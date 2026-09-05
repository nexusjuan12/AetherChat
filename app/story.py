"""
Multiplayer/group "story" mode: multi-character scene setup, the master-
storyteller completion loop, and the koboldcpp multiplayer-story passthrough
routes used for cross-client story state sync. Moved out of the original
monolithic webserver.py.

Two confirmed pre-existing bugs, carried forward as-is (not introduced by
this split - grep the original file, they're there):
- prepare_story_context() is dead code (never called anywhere) and would
  raise NameError if it were, since it references a bare `story` name that
  isn't one of its parameters.
- get_story_state()/update_story() call compress_story_data()/
  decompress_story_data(), which are never defined anywhere in this
  codebase - both routes always fail with a caught NameError -> 500. The
  `base64`/`lzma` imports in the original file's header suggest this was
  meant to be implemented but never was.
"""
import os
import json
import uuid

import requests
from flask import (
    Blueprint, request, jsonify, redirect, url_for, render_template,
    make_response,
)
from flask_login import login_required, current_user

import config
from .extensions import db
from .models import StorySession, StoryCharacter, Character, CreditTransaction
from .media import kobold_handler, handle_kobold_error, require_kobold

bp = Blueprint('story', __name__)

CHARACTER_FOLDER = config.CHARACTER_FOLDER
KOBOLD_API = os.getenv('KOBOLD_API', 'http://127.0.0.1:5000')


def prepare_story_context(character, messages, scenario, other_characters):
    base_context = {
        'role': 'system',
        'content': f"""You are {character.name}. {character.system_prompt}

Current Story Setting:
{scenario}

Current Speaker: {character.name}
Player Character: {story.settings.get('userName', 'User')}
Player's Role: {story.settings.get('userPersona', 'A participant in the story')}

Other Characters Present:
{format_character_list(other_characters)}

Story Context Rules:
- You are ONLY speaking when it's natural for {character.name} to respond
- Never speak for other characters or the player character
- Remember previous interactions and maintain story consistency"""
    }

    recent_context = get_relevant_messages(messages, max_tokens=8000)
    return [base_context] + recent_context

def extract_character_traits(character):
    """Parse character settings for key traits and characteristics"""
    if character.settings and 'traits' in character.settings:
        return character.settings['traits']
    return "No specific traits defined"

def format_character_list(characters):
    """Format information about other characters in the scene"""
    return "\n".join([
        f"- {char.name}: {char.description[:100]}..."
        for char in characters
    ])

def get_relevant_messages(messages, max_tokens=2000):
    """
    Implement smart context window that keeps relevant interactions
    while staying within token limits.
    """
    relevant_messages = []
    token_count = 0
    
    # Process messages in reverse to prioritize recent context
    for msg in reversed(messages):
        estimated_tokens = len(msg['content'].split()) * 1.3  # Rough token estimate
        if token_count + estimated_tokens > max_tokens:
            break
        
        relevant_messages.insert(0, msg)
        token_count += estimated_tokens
        
    return relevant_messages

class StorySetup:
    def __init__(self, title, creator_id):
        self.id = str(uuid.uuid4())
        self.title = title
        self.creator_id = creator_id
        self.characters = []
        self.scenario = ""
        self.themes = []
        self.relationships = {}
        self.scene_settings = {}

PLACEHOLDER_IMAGE = "./assets/placeholders/placeholder.jpg"

PLACEHOLDER_NAME = "Empty Panel"

def parse_character_responses(narrative, valid_characters):
    """
    Parse character responses with improved handling for length and completeness.
    
    Args:
        narrative (str): Raw narrative text
        valid_characters (list): List of tuples containing (character_data, story_character)
    """
    responses = []
    lines = narrative.split('\n')
    current_char = None
    current_content = []
    max_response_length = 150  # Characters, not tokens
    
    for line in lines:
        if ':' not in line:
            if current_char and current_content:
                current_content.append(line)
            continue

        char_name, content = line.split(':', 1)
        char_name = char_name.strip()

        # Check if this is a valid character
        if char_name in [c[0]['name'] for c in valid_characters]:
            # Process previous character's response if exists
            if current_char and current_content:
                response_text = ' '.join(current_content).strip()
                
                # Truncate if too long while preserving complete sentences
                if len(response_text) > max_response_length:
                    sentences = response_text.split('.')
                    truncated = ''
                    for sent in sentences:
                        if len(truncated) + len(sent) <= max_response_length:
                            truncated += sent + '.'
                        else:
                            break
                    response_text = truncated.strip()
                
                # Ensure asterisk expressions are properly closed
                if response_text.count('*') % 2 == 1:
                    response_text = response_text.replace('*', '')
                
                responses.append((current_char, response_text))
            
            current_char = char_name
            current_content = [content.strip()]
            continue

    # Process the last character's response
    if current_char and current_content:
        response_text = ' '.join(current_content).strip()
        if len(response_text) > max_response_length:
            sentences = response_text.split('.')
            truncated = ''
            for sent in sentences:
                if len(truncated) + len(sent) <= max_response_length:
                    truncated += sent + '.'
                else:
                    break
            response_text = truncated.strip()
            
        if response_text.count('*') % 2 == 1:
            response_text = response_text.replace('*', '')
            
        responses.append((current_char, response_text))

    return responses

def generate_character_prompt(story, characters):
    """
    Generate a more focused prompt for character interactions.
    """
    character_list = "\n".join([
        f"- {char[0]['name']}: {char[0].get('description', '')[:100]}..."
        for char in characters
    ])
    
    return f"""You are managing an interactive scene. Setting:
{story.scenario}

Characters present:
{character_list}

Guidelines:
- Keep responses short and focused (1-2 sentences maximum)
- Include either an action OR dialogue, not both
- Avoid repetitive expressions and mannerisms
- Stay in character but be concise
- Never speak for other characters

Format each response as:
CHARACTER_NAME: action/dialogue"""

def process_story_responses(story, valid_characters, user_message, temperature=0.7):
    """
    Process story responses with improved controls.
    """
    try:
        master_prompt = generate_character_prompt(story, valid_characters)
        
        master_response = kobold_handler({
            'model': "koboldcpp",
            'messages': [{'role': 'system', 'content': master_prompt}],
            'temperature': temperature,
            'max_tokens': 150,  # Reduced from 300
            'frequency_penalty': 0.7,  # Increased to reduce repetition
            'presence_penalty': 0.7,
            'stop_sequences': ["\n\n", "###"]
        })

        if not master_response or 'choices' not in master_response:
            raise ValueError("Invalid response from master storyteller")

        narrative = master_response['choices'][0]['message']['content']
        parsed_responses = parse_character_responses(narrative, valid_characters)
        
        responses = []
        for char_name, content in parsed_responses:
            matching_char = next(
                (char for char, _ in valid_characters if char['name'].lower() == char_name.lower()),
                None
            )
            if matching_char:
                char_position = next(
                    sc.position for _, sc in valid_characters 
                    if sc.character_id == matching_char['id']
                )
                responses.append({
                    'character_id': matching_char['id'],
                    'name': matching_char['name'],
                    'content': content,
                    'avatar': matching_char['avatar'],
                    'position': char_position,
                    'ttsVoice': matching_char.get('ttsVoice'),
                    'rvc_model': matching_char.get('rvc_model'),
                    'tts_rate': matching_char.get('tts_rate', 0),
                    'rvc_pitch': matching_char.get('rvc_pitch', 0)
                })

        return responses

    except Exception as e:
        print(f"Error processing story responses: {str(e)}")
        raise

@bp.route('/story/setup', methods=['POST'])
@login_required
def create_story_setup():
    try:
        data = request.json
        
        # Validate minimum character requirement
        active_characters = sum(1 for char in data['characters'] if not char.get('is_placeholder', False))
        if active_characters < 2:
            return jsonify({'error': 'At least two characters are required'}), 400

        # Create new story session
        story = StorySession(
            creator_id=current_user.id,
            title=data['title'],
            scenario=data['scenario'],
            settings={
                'active_character_count': active_characters,
                'placeholder_panels': [i for i, char in enumerate(data['characters']) 
                                    if char.get('is_placeholder', False)]
            }
        )
        db.session.add(story)
        db.session.flush()  # Get the story ID
        
        # Add characters and placeholders
        for char_data in data['characters']:
            position = char_data['position']
            is_placeholder = char_data.get('is_placeholder', False)
            
            story_char = StoryCharacter(
                session_id=story.id,
                character_id=None if is_placeholder else char_data['id'],
                position=position,
                is_placeholder=is_placeholder,
                placeholder_name=PLACEHOLDER_NAME if is_placeholder else None
            )
            db.session.add(story_char)
            
        db.session.commit()
        
        return jsonify({
            'message': 'Story session created successfully',
            'session_id': story.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating story: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/v1/story/completions', methods=['POST'])
@login_required
def story_completions():
    try:
        data = request.json
        session_id = data.get('session_id')
        user_message = data.get('message', '')
        temperature = data.get('temperature', 0.7)
        
        # Get story session and validate
        story = StorySession.query.get_or_404(session_id)
        if story.creator_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Get active characters
        story_chars = StoryCharacter.query.filter_by(
            session_id=session_id,
            is_placeholder=False
        ).order_by(StoryCharacter.position).all()
        
        if not story_chars:
            return jsonify({'error': 'No active characters'}), 400

        # Calculate credits needed
        CREDITS_PER_CHARACTER = 10
        total_credits = CREDITS_PER_CHARACTER * len(story_chars)
        
        # Check credits
        if not current_user.deduct_credits_atomic(total_credits):
            return jsonify({
                'error': 'Insufficient credits',
                'credits_required': total_credits,
                'credits_available': current_user.credits
            }), 402

        # Create credit transaction
        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-total_credits,
            transaction_type='story_interaction',
            description=f'Story interaction in: {story.title}'
        )
        db.session.add(transaction)

        try:
            # Load character data
            print("\nLoading character data...")
            valid_characters = []
            for story_char in story_chars:
                char_file_path = os.path.join(CHARACTER_FOLDER, f"{story_char.character_id}.json")
                if os.path.exists(char_file_path):
                    with open(char_file_path, 'r', encoding='utf-8') as f:
                        char_data = json.load(f)
                        valid_characters.append((char_data, story_char))
                        print(f"Loaded character: {char_data['name']}")

            if not valid_characters:
                raise ValueError("No valid characters found")

            # Process responses using new function
            responses = process_story_responses(
                story=story,
                valid_characters=valid_characters,
                user_message=user_message,
                temperature=temperature
            )

            # Commit transaction and return responses
            db.session.commit()
            return jsonify({'responses': responses})

        except Exception as e:
            # Refund credits on error
            current_user.add_credits(total_credits)
            db.session.delete(transaction)
            db.session.commit()
            raise e

    except Exception as e:
        print(f"Error in story_completions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/setup-story', methods=['GET'])
@login_required
def setup_story_page():
    try:
        response = make_response(render_template('setup-story.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering setup-story page: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/story/sessions')
@login_required
def get_story_sessions():
    try:
        sessions = StorySession.query.filter_by(
            creator_id=current_user.id,
            is_active=True
        ).all()
        
        return jsonify([{
            'id': session.id,
            'title': session.title,
            'scenario': session.scenario,
            'characters': [{
                'id': char.character_id,
                'name': Character.query.get(char.character_id).name if char.character_id 
                        else PLACEHOLDER_NAME,
                'avatar': (Character.query.get(char.character_id).avatar_path if char.character_id 
                         else PLACEHOLDER_IMAGE),
                'position': char.position,
                'is_placeholder': char.is_placeholder
            } for char in StoryCharacter.query.filter_by(session_id=session.id).order_by(StoryCharacter.position).all()]
        } for session in sessions])
        
    except Exception as e:
        print(f"Error getting story sessions: {str(e)}")
        return jsonify([])

@bp.route('/story/<session_id>')
@login_required
def story_chat_page(session_id):
    try:
        # Verify the story session exists and user has access
        story = StorySession.query.get_or_404(session_id)
        
        if story.creator_id != current_user.id:
            return redirect(url_for('static_routes.serve_index'))
            
        response = make_response(render_template('story-chat.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error rendering story chat page: {str(e)}")
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/story/sessions/<session_id>')
@login_required
def get_story_session(session_id):
    try:
        story = StorySession.query.get_or_404(session_id)
        
        # Verify user has access to this story
        if story.creator_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Get characters in this story
        story_characters = StoryCharacter.query.filter_by(
            session_id=session_id
        ).order_by(StoryCharacter.position).all()
        
        # Format character data
        characters = []
        for sc in story_characters:
            if sc.is_placeholder:
                characters.append({
                    'id': None,
                    'position': sc.position,
                    'is_placeholder': True,
                    'name': sc.placeholder_name or "Empty Panel",
                    'avatar': './avatars/default-user.png',  # Use absolute path
                    'background': './assets/default-bg.jpg'  # Use absolute path
                })
            else:
                try:
                    # Load character data from JSON file for complete information
                    char_file_path = os.path.join(CHARACTER_FOLDER, f"{sc.character_id}.json")
                    if os.path.exists(char_file_path):
                        with open(char_file_path, 'r', encoding='utf-8') as f:
                            char_data = json.load(f)
                            
                        # Ensure paths start with ./
                        avatar_path = char_data.get('avatar', './avatars/default-user.png')
                        if not avatar_path.startswith('./'):
                            avatar_path = f"./{avatar_path}"
                            
                        background_path = char_data.get('background')
                        if background_path and not background_path.startswith('./'):
                            background_path = f"./{background_path}"
                            
                        characters.append({
                            'id': sc.character_id,
                            'position': sc.position,
                            'name': char_data.get('name', 'Unknown Character'),
                            'avatar': avatar_path,
                            'background': background_path or './assets/default-bg.jpg',
                            'is_placeholder': False,
                            'ttsVoice': char_data.get('ttsVoice'),
                            'rvc_model': char_data.get('rvc_model'),
                            'tts_rate': char_data.get('tts_rate', 0),
                            'rvc_pitch': char_data.get('rvc_pitch', 0)
                        })
                except Exception as e:
                    print(f"Error loading character {sc.character_id}: {str(e)}")
                    # Fallback to database record
                    char = Character.query.get(sc.character_id)
                    if char:
                        characters.append({
                            'id': char.id,
                            'position': sc.position,
                            'name': char.name,
                            'avatar': './avatars/default-user.png',
                            'background': './assets/default-bg.jpg',
                            'is_placeholder': False,
                            'ttsVoice': char.tts_voice,
                            'rvc_model': char.settings.get('rvc_model') if char.settings else None,
                            'tts_rate': char.settings.get('tts_rate', 0) if char.settings else 0,
                            'rvc_pitch': char.settings.get('rvc_pitch', 0) if char.settings else 0
                        })
        
        return jsonify({
            'id': story.id,
            'title': story.title,
            'scenario': story.scenario,
            'characters': characters,
            'settings': story.settings
        })
        
    except Exception as e:
        print(f"Error getting story session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/v1/story/user-message', methods=['POST'])
@login_required
def generate_user_message():
    try:
        data = request.json
        session_id = data.get('session_id')
        messages = data.get('messages', [])
        temperature = data.get('temperature', 0.8)
        
        story = StorySession.query.get_or_404(session_id)
        if story.creator_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Create context from story settings and previous messages
        context = f"""
Story Setting: {story.scenario}

User's Character: {story.settings.get('userName', 'User')}
User's Role: {story.settings.get('userPersona', 'A participant in the story')}

Previous messages:
{' '.join([msg['content'] for msg in messages[-5:]])}  # Last 5 messages for context

Generate a natural response from the user's perspective that advances the story.
The response should:
1. Be relevant to the ongoing conversation
2. Consider the user's character and role
3. Help move the story forward
4. Be between 1-3 sentences
5. Not be repetitive or generic

Generate only the user's message without any additional explanation or context."""

        # Generate user message using Kobold
        response = kobold_handler({
            'model': "koboldcpp",
            'messages': [{'role': 'system', 'content': context}],
            'temperature': temperature,
            'max_tokens': 100,
            'stop': ["\n", "Character:", "User:"]
        })

        if not response or 'choices' not in response:
            return jsonify({'error': 'Failed to generate message'}), 500

        message = response['choices'][0]['message']['content'].strip()
        
        # Cost 5 credits for message generation
        if not current_user.deduct_credits_atomic(5):
            return jsonify({
                'error': 'Insufficient credits',
                'credits_required': 5,
                'credits_available': current_user.credits
            }), 402

        # Record transaction
        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-5,
            transaction_type='endless_mode_message',
            description=f'Generated user message in endless mode'
        )
        db.session.add(transaction)
        db.session.commit()

        return jsonify({'message': message})

    except Exception as e:
        print(f"Error generating user message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/extra/multiplayer/getstory', methods=['POST'])
@login_required
def get_multiplayer_story():
    try:
        response = requests.post(f'{KOBOLD_API}/api/extra/multiplayer/getstory')
        if not response.ok:
            return handle_kobold_error(response)
        # Just pass through the raw response text
        return response.text, response.status_code, {'Content-Type': response.headers.get('Content-Type', 'text/plain')}
    except Exception as e:
        print(f"Error getting story: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/extra/multiplayer/setstory', methods=['POST'])
@login_required
@require_kobold
def set_multiplayer_story():
    try:
        response = requests.post(
            f'{KOBOLD_API}/api/extra/multiplayer/setstory',
            json=request.json
        )
        if not response.ok:
            return handle_kobold_error(response)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        print(f"Error setting story: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/v1/story/state', methods=['GET'])
@login_required
def get_story_state():
    try:
        response = requests.get(f'{KOBOLD_API}/api/extra/multiplayer/getstory')
        if response.ok:
            story_data = response.json()
            if 'data' in story_data:
                decompressed_data = decompress_story_data(story_data['data'])
                return jsonify(decompressed_data)
        return jsonify({'error': 'Failed to get story state'}), response.status_code
    except Exception as e:
        print(f"Error getting story state: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/v1/story/update', methods=['POST'])
@login_required
def update_story():
    try:
        story_data = request.json
        compressed_data = compress_story_data(story_data)
        
        payload = {
            "full_update": True,
            "sender": f"USER_{current_user.id}",
            "data_format": "kcpp_lzma_b64",
            "data": compressed_data
        }

        response = requests.post(
            f'{KOBOLD_API}/api/extra/multiplayer/setstory',
            json=payload
        )

        if not response.ok:
            return jsonify({'error': 'Failed to update story'}), response.status_code

        return jsonify(response.json())

    except Exception as e:
        print(f"Error updating story: {str(e)}")
        return jsonify({'error': str(e)}), 500
