import zipfile  # built-in
import py7zr
import rarfile
import tempfile
import os
import shutil
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, make_response
from datetime import datetime, timedelta
import shutil
import json
from flask import Flask, request, jsonify, send_from_directory, send_file, Response, session, g
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import threading
import requests
import time
import uuid
from dotenv import load_dotenv
from tts_with_rvc import TTS_RVC
from flask_talisman import Talisman
from flask_cors import CORS, cross_origin
import stripe
from sqlalchemy import and_
import time
from queue_system import request_queue, setup_queue_handlers
from model_cache import model_cache
import base64
import lzma
import json
from functools import wraps

# Load environment variables
load_dotenv('/root/.env')

app = Flask(__name__,
    template_folder='/root/templates',
    static_folder='/root/main'
)
CORS(app, 
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": ["*"],  # Allow all origins for local deployment
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    }
)

model_cache._base_model_path = "/root/models"
model_cache._input_dir = "/root/input/"
model_cache._output_dir = "/root/output/"
model_cache._cache_timeout = 1800  # 30 minutes timeout

# App Configuration
app.config.update(
    SQLALCHEMY_DATABASE_URI='sqlite:////root/db/users.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-key-change-this'),
    STATIC_FOLDER='/root/main',
    SESSION_COOKIE_SECURE=False,  # Changed for local deployment
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=31),
    SESSION_COOKIE_PATH='/',
    MAX_CONTENT_LENGTH=1024 * 1024 * 1024,
)
    
# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PRICE_IDS = {
    'creator': os.getenv('STRIPE_CREATOR_PRICE_ID'),  # $9.99 monthly
    'master': os.getenv('STRIPE_MASTER_PRICE_ID'),    # $24.99 monthly
}

# Credit package configuration
CREDIT_PACKAGES = {
    1000: 500,   # 1000 credits for $5.00
    2500: 1000   # 2500 credits for $10.00
}

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.unauthorized_handler
def unauthorized():
    if request.blueprint == 'api' or request.path.startswith('/api/') or request.path.startswith('/auth/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('serve_index'))

# Directory configurations
STATIC_DIR = "/root/main"
OUTPUT_DIRECTORY = "/root/output/"
UPLOAD_FOLDER = '/root/main/avatars'
CHARACTER_FOLDER = '/root/main/characters'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'wmv'}
KOBOLD_API = os.getenv('KOBOLD_API', 'http://127.0.0.1:5000')


os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CHARACTER_FOLDER, exist_ok=True)
# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    credits = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False) 
    characters = db.relationship('Character', backref='creator', lazy=True)
    stripe_customer_id = db.Column(db.String(100), unique=True)
    subscription_tier = db.Column(db.String(20), default='explorer')
    subscription_status = db.Column(db.String(20), default='free')
    subscription_id = db.Column(db.String(100), unique=True)
    monthly_credits = db.Column(db.Integer, default=1000)
    last_credit_refresh = db.Column(db.DateTime, default=datetime.utcnow)

    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_credits(self):
        return self.credits
    
    def add_credits(self, amount):
        self.credits += amount
        db.session.commit()
        
    def deduct_credits(self, amount):
        if self.credits >= amount:
            self.credits -= amount
            db.session.commit()
            return True
        return False

    # Add the new method here, indented at the same level as the others
    def deduct_credits_atomic(self, amount):
        """
        Atomically deduct credits from user balance.
        Returns True if successful, False if insufficient credits.
        """
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                # Create a new session for this transaction
                with db.session.begin():
                    user = db.session.query(User).filter(
                        User.id == self.id
                    ).with_for_update().first()

                    if not user or user.credits < amount:
                        return False

                    # Update credits directly in the transaction
                    user.credits = user.credits - amount
                    return True

            except Exception as e:
                db.session.rollback()
                if attempt == max_retries - 1:
                    print(f"Error in atomic credit deduction: {e}")
                    return False
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff

        return False  # All retries failed
        return False  # All retries failed

class StorySession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    scenario = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    max_characters = db.Column(db.Integer, default=4)
    settings = db.Column(db.JSON)

class StoryCharacter(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey('story_session.id'), nullable=False)
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'), nullable=True)  # Nullable for placeholders
    position = db.Column(db.Integer)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_placeholder = db.Column(db.Boolean, default=False)
    placeholder_name = db.Column(db.String(100), default="Empty Panel")


class StripeTransaction(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # Amount in cents
    credits = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'credit_purchase' or 'subscription'
    status = db.Column(db.String(20), nullable=False)
    stripe_payment_id = db.Column(db.String(100), unique=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Changed backref name to avoid conflict
    user = db.relationship('User', backref=db.backref('stripe_payment_transactions', lazy=True))

class SubscriptionTier(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(50), nullable=False)  # 'explorer', 'creator', 'master'
    price = db.Column(db.Integer, nullable=False)    # Price in cents
    monthly_credits = db.Column(db.Integer)          # None for unlimited
    features = db.Column(db.JSON)


# Credit Transaction Model
class CreditTransaction(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

class Character(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    avatar_path = db.Column(db.String(255), nullable=False)
    background_path = db.Column(db.String(255))
    tts_voice = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50))
    is_private = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    settings = db.Column(db.JSON)
    greetings = db.Column(db.JSON) 

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar_path,
            'background': self.background_path,
            'category': self.category,
            'is_private': self.is_private,
            'is_approved': self.is_approved,
            'created_at': self.created_at.isoformat(),
            'settings': self.settings
        }

class CharacterApprovalQueue(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    reviewer_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    review_notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    
    character = db.relationship('Character')
    reviewer = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'character': self.character.to_dict(),
            'submitted_at': self.submitted_at.isoformat(),
            'status': self.status,
            'review_notes': self.review_notes,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS 
        
def kobold_handler(data):
    """Handle Kobold API requests"""
    try:
        # Your existing Kobold API call
        kobold_response = requests.post(
            'http://127.0.0.1:5000/v1/chat/completions', 
            json=data
        )
        return kobold_response.json()
    except Exception as e:
        raise Exception(f"Kobold API error: {str(e)}")

def check_kobold_available():
    """Check if KoboldCPP API is available"""
    try:
        response = requests.get(f'{KOBOLD_API}/api/v1/model')
        return response.ok
    except:
        return False

def handle_kobold_error(response):
    """Handle error responses from KoboldCPP"""
    try:
        error_data = response.json()
        return jsonify({
            'error': 'KoboldCPP API error',
            'details': error_data.get('detail', str(response.status_code))
        }), response.status_code
    except:
        return jsonify({
            'error': 'KoboldCPP API error',
            'details': str(response.status_code)
        }), response.status_code

def require_kobold(f):
    """Decorator to check if KoboldCPP is available"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_kobold_available():
            return jsonify({
                'error': 'KoboldCPP API is not available'
            }), 503
        return f(*args, **kwargs)
    return decorated_function

def tts_handler(data):
    try:
        print("TTS handler received data:", data)
        text = data.get("text")
        character_id = data.get("rvc_model")
        edge_voice = data.get("edge_voice")
        tts_rate = data.get("tts_rate", 0)
        rvc_pitch = data.get("rvc_pitch", 0)

        # Get TTS instance from cache
        tts = model_cache.get_model(character_id)
        
        unique_id = str(uuid.uuid4())
        output_filename = f"response_{unique_id}.wav"
        output_path = os.path.join(OUTPUT_DIRECTORY, output_filename)

        # Set voice and generate audio
        if edge_voice:
            tts.set_voice(edge_voice)
            
        tts(
            text=text,
            pitch=rvc_pitch,
            tts_rate=tts_rate,
            output_filename=output_path
        )

        if not os.path.exists(output_path):
            raise Exception("Failed to generate audio file")

        return {"audio_url": f"/audio/{output_filename}"}

    except Exception as e:
        print(f"TTS handler error: {str(e)}")
        traceback.print_exc()
        raise Exception(f"TTS error: {str(e)}")

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

@app.route('/story/setup', methods=['POST'])
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

@app.route('/v1/story/completions', methods=['POST'])
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
        
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Authentication Routes
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
        
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already taken'}), 409
        
    user = User(
        username=data['username'],
        email=f"{data['username']}@temp.com",  # Temporary email since model requires it
        created_at=datetime.utcnow()
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        session.permanent = True
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'credits': user.credits,
                'is_admin': user.is_admin
            }
        }), 201
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
        

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing credentials'}), 400
        
    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        login_user(user, remember=True)
        session.permanent = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'credits': user.credits,
                'is_admin': user.is_admin
            }
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401
    
@app.route('/auth/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/auth/user')
@login_required
def get_user():
    return jsonify({
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'username': current_user.username,
            'credits': current_user.credits,  # Added missing comma here
            'is_admin': current_user.is_admin
        }
    }), 200

# Static Routes
@app.route('/')
def serve_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        # Strip any route prefixes
        if path.startswith('edit-character/'):
            path = path.replace('edit-character/', '', 1)
        if path.startswith('admin-dashboard/'):  # Add this line
            path = path.replace('admin-dashboard/', '', 1)  # Add this line
        if path.startswith('css/') or path.startswith('js/'):
            return send_from_directory(STATIC_DIR, path)
        return send_from_directory(STATIC_DIR, path)
    except Exception as e:
        print(f"Error serving {path}: {e}")
        return f"Error: Could not serve {path}", 404

@app.route('/chat/<path:filename>')
def serve_chat_files(filename):
    try:
        # Map extensions to MIME types
        mime_types = {
            'js': 'application/javascript',
            'css': 'text/css',
            'html': 'text/html'
        }
        
        # Get file extension
        ext = filename.split('.')[-1]
        mime_type = mime_types.get(ext, 'text/plain')
        
        # Send file with correct MIME type
        response = send_from_directory(os.path.join(STATIC_DIR, 'chat'), filename)
        response.headers['Content-Type'] = mime_type
        return response
    except Exception as e:
        print(f"Error serving chat file {filename}: {e}")
        return f"Error: Could not serve {filename}", 404

        
@app.route('/v1/tts', methods=['POST'])
@login_required
def tts():
    if request.method == 'OPTIONS':
        return handle_options()

    try:
        CREDITS_PER_TTS = 5
        
        # Check if user has enough credits
        if not current_user.deduct_credits_atomic(CREDITS_PER_TTS):
            return jsonify({
                'error': 'Insufficient credits',
                'credits_required': CREDITS_PER_TTS,
                'credits_available': current_user.credits
            }), 402

        # Create transaction record
        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-CREDITS_PER_TTS,
            transaction_type='tts',
            description='Text-to-speech conversion'
        )
        db.session.add(transaction)

        # Add request to queue
        data = request.json
        request_id = request_queue.add_request(current_user.id, 'tts', data)
        
        # Check initial status
        status = request_queue.get_status(request_id)
        
        if status['status'] == 'queued' and status['position'] > 3:
            return jsonify({
                'status': 'queued',
                'position': status['position'],
                'request_id': request_id
            })
        
        # Poll for completion if position is low
        max_attempts = 30
        for _ in range(max_attempts):
            status = request_queue.get_status(request_id)
            if status['status'] == 'complete':
                db.session.commit()
                return jsonify(status['result'])
            elif status['status'] == 'error':
                current_user.add_credits(CREDITS_PER_TTS)
                db.session.delete(transaction)
                db.session.commit()
                return jsonify({'error': status['result']['error']}), 500
            time.sleep(1)
        
        # Timeout - refund credits
        current_user.add_credits(CREDITS_PER_TTS)
        db.session.delete(transaction)
        db.session.commit()
        return jsonify({'error': 'Request timeout'}), 408

    except Exception as e:
        if 'transaction' in locals():
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
        return jsonify({'error': str(e)}), 500

@app.route('/v1/chat/status/<request_id>')
@login_required
def check_chat_status(request_id):
    status = request_queue.get_status(request_id)
    if not status:
        return jsonify({'error': 'Request not found'}), 404
    return jsonify(status)

@app.route('/v1/chat/completions', methods=['POST'])
@login_required
def chat_completions():
    if request.method == 'OPTIONS':
        return handle_options()

    try:
        CREDITS_PER_MESSAGE = 10
        
        # Check if user has enough credits
        if not current_user.deduct_credits_atomic(CREDITS_PER_MESSAGE):
            return jsonify({
                'error': 'Insufficient credits',
                'credits_required': CREDITS_PER_MESSAGE,
                'credits_available': current_user.credits
            }), 402

        # Create transaction record
        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-CREDITS_PER_MESSAGE,
            transaction_type='message',
            description='Chat completion message'
        )
        db.session.add(transaction)

        # Add request to queue
        data = request.json
        request_id = request_queue.add_request(current_user.id, 'chat', data)
        
        # Check initial status
        status = request_queue.get_status(request_id)
        
        if status['status'] == 'queued' and status['position'] > 3:
            # Return queued status if position is high
            return jsonify({
                'status': 'queued',
                'position': status['position'],
                'request_id': request_id
            })
        
        # Poll for completion if position is low
        max_attempts = 30  # 30 second timeout
        for _ in range(max_attempts):
            status = request_queue.get_status(request_id)
            if status['status'] == 'complete':
                db.session.commit()  # Commit the transaction
                return jsonify(status['result'])
            elif status['status'] == 'error':
                # Refund credits on error
                current_user.add_credits(CREDITS_PER_MESSAGE)
                db.session.delete(transaction)
                db.session.commit()
                return jsonify({'error': status['result']['error']}), 500
            time.sleep(1)
        
        # Timeout - refund credits
        current_user.add_credits(CREDITS_PER_MESSAGE)
        db.session.delete(transaction)
        db.session.commit()
        return jsonify({'error': 'Request timeout'}), 408
        
    except Exception as e:
        if 'transaction' in locals():
            current_user.add_credits(CREDITS_PER_MESSAGE)
            db.session.delete(transaction)
            db.session.commit()
        return jsonify({'error': str(e)}), 500
        
# Create Character Routes
@app.route('/create-character', methods=['GET', 'POST'])
@login_required
def create_character_page():
    try:
        response = make_response(render_template('create-character.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering create-character page: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('serve_index'))

@app.route('/characters/create', methods=['POST'])
@login_required
def create_character():
    try:
        data = request.json
        print("Received data:", data)
        
        char_id = data.get('id', str(uuid.uuid4()))
        is_private = data.get('is_private', False)
        
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400
            
        if not data.get('avatar'):
            return jsonify({'error': 'Avatar is required'}), 400
            
        # Handle greeting/greetings conversion
        greetings = []
        if data.get('greeting'):  # If a single greeting is provided
            greetings.append(data['greeting'])
        elif data.get('greetings'):  # If greetings array is provided
            greetings = data['greetings']

        # Prepare AI parameters
        ai_parameters = {
            'temperature': 0.8,
            'max_tokens': 150,
            'top_p': 0.9,
            'presence_penalty': 0.6,
            'frequency_penalty': 0.6
        }
        if data.get('ai_parameters'):
            ai_parameters.update(data['ai_parameters'])

        # Prepare settings
        settings = {
            'tts_rate': data.get('tts_rate', 0),
            'rvc_pitch': data.get('rvc_pitch', 0),
            'ai_parameters': ai_parameters,
            'tags': data.get('tags', [])
        }
            
        character = Character(
            id=char_id,
            creator_id=current_user.id,
            name=data['name'],
            description=data.get('description', ''),
            system_prompt=data.get('systemPrompt', ''),
            greetings=greetings,
            avatar_path=data['avatar'],
            background_path=data.get('background'),
            tts_voice=data.get('ttsVoice', ''),
            category=data.get('category', 'Other'),
            is_private=is_private,
            is_approved=is_private,
            approval_status='approved' if is_private else 'pending',
            settings=settings
        )
        
        try:
            db.session.add(character)
            db.session.flush()
            print("Character added to database")
        except Exception as db_error:
            print("Database error:", str(db_error))
            raise
            
        try:
            # Create character JSON file
            char_file_data = {
                'id': char_id,
                'name': data['name'],
                'avatar': data['avatar'],
                'description': data.get('description', ''),
                'systemPrompt': data.get('systemPrompt', ''),
                'greetings': greetings,
                'ttsVoice': data.get('ttsVoice', ''),
                'category': data.get('category', 'Other'),
                'tags': data.get('tags', []),
                'tts_rate': data.get('tts_rate', 0),
                'rvc_pitch': data.get('rvc_pitch', 0),
                'dateAdded': datetime.utcnow().isoformat(),
                'creator': current_user.id,
                'isPrivate': is_private,
                'isApproved': is_private,
                'approvalStatus': 'approved' if is_private else 'pending',
                'ai_parameters': ai_parameters
            }
            
            if data.get('background'):
                char_file_data['background'] = data['background']

            if data.get('rvc_model'):
                char_file_data['rvc_model'] = data['rvc_model']
            
            # Save character JSON file
            char_file_path = os.path.join(CHARACTER_FOLDER, f"{char_id}.json")
            with open(char_file_path, 'w', encoding='utf-8') as f:
                json.dump(char_file_data, f, indent=2)
            print("Character JSON file created")
            
            db.session.commit()
            print("Database committed")
            
            # Award credits
            current_user.add_credits(200)
            transaction = CreditTransaction(
                user_id=current_user.id,
                amount=200,
                transaction_type='character_creation',
                description=f'Created {"private" if is_private else "public"} character: {data["name"]}'
            )
            db.session.add(transaction)
            db.session.commit()
            print("Credits awarded")
            
            return jsonify({
                'message': 'Character created successfully',
                'character_id': char_id,
                'approval_status': 'approved' if is_private else 'pending',
                'credits_earned': 200
            }), 201
            
        except Exception as e:
            print("Error saving character file:", str(e))
            raise
            
    except Exception as e:
        db.session.rollback()
        print("Error creating character:", str(e))
        print("Error type:", type(e))
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500



# Get public characters
@app.route('/characters/public')
def get_public_characters():
    try:
        public_characters = []
        if os.path.exists(CHARACTER_FOLDER):
            for filename in os.listdir(CHARACTER_FOLDER):
                if filename.endswith('.json'):
                    try:
                        with open(os.path.join(CHARACTER_FOLDER, filename), 'r', encoding='utf-8') as f:
                            char_data = json.load(f)
                            if not char_data.get('isPrivate', False) and char_data.get('isApproved', False):
                                public_characters.append(char_data)
                    except Exception as e:
                        print(f"Error reading character file {filename}: {str(e)}")
                        continue
        return jsonify(public_characters)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get private characters for current user
@app.route('/characters/private')
@login_required
def get_private_characters():
    try:
        characters = Character.query.filter_by(
            creator_id=current_user.id,
            is_private=True
        ).all()
        return jsonify([{
            'id': char.id,
            'name': char.name,
            'description': char.description,
            'avatar': char.avatar,
            'category': char.category
        } for char in characters])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin routes for character approval
@app.route('/admin/characters/pending')
@login_required
def get_pending_characters():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        pending_characters = []
        if os.path.exists(CHARACTER_FOLDER):
            for filename in os.listdir(CHARACTER_FOLDER):
                if filename.endswith('.json'):
                    try:
                        with open(os.path.join(CHARACTER_FOLDER, filename), 'r', encoding='utf-8') as f:
                            char_data = json.load(f)
                            # Add debug logging
                            print(f"Character data: {char_data}")
                            
                            if not char_data.get('isPrivate', False) and \
                               not char_data.get('isApproved', False) and \
                               char_data.get('approvalStatus') == 'pending':
                                # Create character object with explicit background field
                                char_obj = {
                                    'id': char_data.get('id', filename.replace('.json', '')),
                                    'name': char_data.get('name', 'Unknown'),
                                    'description': char_data.get('description', ''),
                                    'avatar': char_data.get('avatar', ''),
                                    'background': char_data.get('background', ''),  # Make sure this matches the JSON field name
                                    'category': char_data.get('category', 'Other'),
                                    'creator_id': char_data.get('creator'),
                                    'approvalStatus': char_data.get('approvalStatus', 'pending')
                                }
                                print(f"Adding pending character: {char_obj}")  # Debug log
                                pending_characters.append(char_obj)
                    except Exception as e:
                        print(f"Error reading character file {filename}: {str(e)}")
                        continue
        
        print(f"Total pending characters: {len(pending_characters)}")  # Debug log
        return jsonify(pending_characters)
    except Exception as e:
        print(f"Error in get_pending_characters: {str(e)}")
        return jsonify([])

@app.route('/admin/characters/<character_id>/approve', methods=['POST'])
@login_required
def approve_character(character_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        # Update JSON file first
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        if not os.path.exists(char_file_path):
            return jsonify({'error': 'Character not found'}), 404

        with open(char_file_path, 'r+', encoding='utf-8') as f:
            char_data = json.load(f)
            char_data['isApproved'] = True
            char_data['approvalStatus'] = 'approved'
            if 'rejectionReason' in char_data:
                del char_data['rejectionReason']
            
            # Reset file pointer and write updated data
            f.seek(0)
            json.dump(char_data, f, indent=2)
            f.truncate()

        # Update database record if it exists
        character = Character.query.get(character_id)
        if character:
            character.is_approved = True
            character.approval_status = 'approved'
            
            # Award credits to creator
            creator = User.query.get(character.creator_id)
            if creator:
                creator.add_credits(500)
                transaction = CreditTransaction(
                    user_id=creator.id,
                    amount=500,
                    transaction_type='character_approval',
                    description=f'Character approved: {character.name}'
                )
                db.session.add(transaction)
            
            db.session.commit()

        return jsonify({'message': 'Character approved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/characters/<character_id>/reject', methods=['POST'])
@login_required
def reject_character(character_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        data = request.json
        reason = data.get('reason', 'No reason provided')
        
        # Update database
        character = Character.query.get_or_404(character_id)
        character.approval_status = 'rejected'
        character.is_approved = False
        
        # Update JSON file
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        if os.path.exists(char_file_path):
            with open(char_file_path, 'r+', encoding='utf-8') as f:
                data = json.load(f)
                data['approvalStatus'] = 'rejected'
                data['isApproved'] = False
                data['rejectionReason'] = reason
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
        
        db.session.commit()
        return jsonify({'message': 'Character rejected', 'reason': reason})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/upload/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
        
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    if file and allowed_file(file.filename):
        # Get character ID instead of name for consistency
        character_id = file.filename.split('-')[0]
        filename = f"{character_id}-avatar.png"  # Use character ID consistently
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return jsonify({'avatarPath': f'./avatars/{filename}'}), 200
    
    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/upload/character-background', methods=['POST'])
@login_required
def upload_background():
    if 'background' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
        
    file = request.files['background']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    if file and allowed_file(file.filename):
        # Get character ID from form data
        character_id = request.form.get('characterId')
        
        # Create character directory
        char_dir = os.path.join(CHARACTER_FOLDER, character_id)
        os.makedirs(char_dir, exist_ok=True)
        
        # Clean up existing background files
        for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'wmv']:
            old_file = os.path.join(char_dir, f'background.{ext}')
            if os.path.exists(old_file):
                try:
                    os.remove(old_file)
                    print(f"Removed old background: {old_file}")
                except Exception as e:
                    print(f"Error removing old background {old_file}: {e}")

        # Clean up old thumbnail if it exists
        old_thumb = os.path.join(char_dir, 'background_thumb.jpg')
        if os.path.exists(old_thumb):
            try:
                os.remove(old_thumb)
                print(f"Removed old thumbnail: {old_thumb}")
            except Exception as e:
                print(f"Error removing old thumbnail: {e}")
        
        # Save new file with original extension
        original_ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"background.{original_ext}"
        filepath = os.path.join(char_dir, filename)
        file.save(filepath)
        
        response_data = {
            'backgroundPath': f'./characters/{character_id}/background.{original_ext}',
            'isVideo': original_ext in ['mp4', 'webm', 'wmv']
        }
        
        # Handle video thumbnail generation
        if original_ext in ['mp4', 'webm', 'wmv']:
            try:
                import cv2
                video = cv2.VideoCapture(filepath)
                success, frame = video.read()
                if success:
                    thumbnail_path = os.path.join(char_dir, 'background_thumb.jpg')
                    cv2.imwrite(thumbnail_path, frame)
                    video.release()
                    response_data['thumbnail'] = f'./characters/{character_id}/background_thumb.jpg'
            except Exception as e:
                print(f"Error creating video thumbnail: {e}")

        # Handle image fallback for non-GIF images
        elif original_ext != 'gif':
            try:
                from PIL import Image
                img = Image.open(filepath)
                jpg_filepath = os.path.join(char_dir, 'background.jpg')
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    background.save(jpg_filepath, 'JPEG', quality=95)
                else:
                    img.convert('RGB').save(jpg_filepath, 'JPEG', quality=95)
                response_data['jpgFallback'] = f'./characters/{character_id}/background.jpg'
            except Exception as e:
                print(f"Error creating JPG fallback: {e}")
            
        return jsonify(response_data), 200
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/check-character/<character_name>')
@login_required
def check_character(character_name):
    # Check if avatar exists
    avatar_path = os.path.join(UPLOAD_FOLDER, f"{character_name}-avatar.png")
    
    # Check if character directory exists
    char_dir = os.path.join(CHARACTER_FOLDER, character_name)
    
    # Check if character JSON exists
    json_path = os.path.join(CHARACTER_FOLDER, f"{character_name}.json")
    
    exists = os.path.exists(avatar_path) or os.path.exists(char_dir) or os.path.exists(json_path)
    
    return jsonify({'exists': exists})

@app.route('/characters/upload-model', methods=['POST'])
@login_required
def upload_model():
    try:
        char_id = request.form.get('characterId')
        if not char_id:
            return jsonify({'error': 'Character ID is required'}), 400

        # Create model directory
        model_dir = os.path.join('/root/models', char_id)
        os.makedirs(model_dir, exist_ok=True)

        # Handle model file upload
        if 'modelFile' in request.files:
            model_file = request.files['modelFile']
            if not model_file.filename.endswith('.pth'):
                return jsonify({'error': 'Invalid model file type. Must be .pth'}), 400
                
            model_path = os.path.join(model_dir, f"{char_id}.pth")
            model_file.save(model_path)
            return jsonify({'message': 'Model file uploaded successfully'})
            
        # Handle index file upload
        elif 'indexFile' in request.files:
            index_file = request.files['indexFile']
            if not index_file.filename.endswith('.index'):
                return jsonify({'error': 'Invalid index file type. Must be .index'}), 400
                
            index_path = os.path.join(model_dir, f"{char_id}.index")
            index_file.save(index_path)
            
            # Check if model file exists
            model_path = os.path.join(model_dir, f"{char_id}.pth")
            if not os.path.exists(model_path):
                return jsonify({'error': 'Model file not found'}), 400
                
            # Update character settings
            character = Character.query.get(char_id)
            if character and character.creator_id == current_user.id:
                if not character.settings:
                    character.settings = {}
                character.settings['rvc_model'] = char_id
                db.session.commit()
                
            return jsonify({
                'message': 'Model upload completed successfully',
                'character_id': char_id
            })
            
        else:
            return jsonify({'error': 'No file provided'}), 400

    except Exception as e:
        print(f"Model upload error: {str(e)}")
        if 'model_dir' in locals() and os.path.exists(model_dir):
            shutil.rmtree(model_dir)
        return jsonify({'error': str(e)}), 500


# Add this helper function for OPTIONS requests
def handle_options():
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Content-Length')
    response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '3600')
    return response

@app.route('/api/available-voices', methods=['GET'])
@login_required
def get_available_voices():
    try:
        edge_voices = [
            "en-GB-LibbyNeural",
            "en-GB-MaisieNeural",
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
            "en-GB-ThomasNeural",
            "en-US-AvaMultilingualNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-EmmaMultilingualNeural",
            "en-US-BrianMultilingualNeural",
            "en-US-AvaNeural",
            "en-US-AndrewNeural",
            "en-US-EmmaNeural",
            "en-US-BrianNeural",
            "en-US-AnaNeural",
            "en-US-AriaNeural",
            "en-US-ChristopherNeural",
            "en-US-EricNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-MichelleNeural",
            "en-US-RogerNeural",
            "en-US-SteffanNeural"
        ]
        
        models_dir = '/root/models'
        rvc_models = []
        
        for model_name in os.listdir(models_dir):
            model_dir = os.path.join(models_dir, model_name)
            if os.path.isdir(model_dir):
                if os.path.exists(os.path.join(model_dir, f"{model_name}.pth")) and \
                   os.path.exists(os.path.join(model_dir, f"{model_name}.index")):
                    rvc_models.append(model_name)
                    
        return jsonify({
            'edge_voices': edge_voices,
            'rvc_models': rvc_models
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/characters/submit-for-review/<character_id>', methods=['POST'])
@login_required
def submit_for_review(character_id):
    try:
        character = Character.query.get_or_404(character_id)
        
        if character.creator_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        approval_request = CharacterApprovalQueue(
            character_id=character_id,
            status='pending'
        )
        
        db.session.add(approval_request)
        db.session.commit()
        
        return jsonify({'message': 'Character submitted for review'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/characters/my-library')
def my_library():
    try:
        all_characters = []
        for filename in os.listdir(CHARACTER_FOLDER):
            if filename.endswith('.json') and filename != 'index.json':
                file_path = os.path.join(CHARACTER_FOLDER, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        char_data = json.load(f)
                        
                        # Add debug logging
                        print(f"Loading character {filename}: Private: {char_data.get('isPrivate')}, Approved: {char_data.get('isApproved')}, Status: {char_data.get('approvalStatus')}")
                        
                        # For non-authenticated users
                        if not current_user.is_authenticated:
                            if not char_data.get('isPrivate') and char_data.get('isApproved'):
                                all_characters.append(char_data)
                            continue

                        # For authenticated users
                        # Show all their own characters
                        if str(char_data.get('creator')) == str(current_user.id):
                            all_characters.append(char_data)
                        # Show public approved characters from others
                        elif not char_data.get('isPrivate') and char_data.get('isApproved'):
                            all_characters.append(char_data)
                except Exception as e:
                    print(f"Error reading character file {filename}: {str(e)}")
                    continue

        # Sort characters into appropriate categories
        response_data = {
            'private': [],
            'public': [],
            'pending': []
        }

        for char in all_characters:
            if char.get('isPrivate'):
                response_data['private'].append(char)
            elif char.get('approvalStatus') == 'pending':
                response_data['pending'].append(char)
            else:
                response_data['public'].append(char)

        print(f"Returning characters: {len(response_data['public'])} public, {len(response_data['private'])} private, {len(response_data['pending'])} pending")
        
        return jsonify(response_data)

    except Exception as e:
        print(f"Error in my_library: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/audio/<filename>', methods=['GET'])
def get_audio(filename):
    file_path = os.path.join(OUTPUT_DIRECTORY, filename)
    print(f"Requested audio file: {file_path}")
    if os.path.exists(file_path):
        print(f"Serving audio file: {file_path}")
        response = send_file(file_path, mimetype="audio/wav")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    print(f"Audio file not found: {file_path}")
    return jsonify({"error": "File not found"}), 404

@app.route('/edit-character/<character_id>')
@login_required
def edit_character_page(character_id):
    try:
        print(f"Attempting to edit character: {character_id}")
        # Load the character data from JSON
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        print(f"Looking for character file at: {char_file_path}")
        
        if not os.path.exists(char_file_path):
            print(f"Character file not found: {char_file_path}")
            return redirect(url_for('serve_index'))
            
        # Read the character data
        with open(char_file_path, 'r', encoding='utf-8') as f:
            char_data = json.load(f)
            print(f"Character data loaded: {char_data}")
            print(f"Current user ID: {current_user.id}")
            print(f"Character creator: {char_data.get('creator')}")
            print(f"Is admin: {current_user.is_admin}")
            
        # Check ownership or admin status
        if str(char_data.get('creator')) != str(current_user.id) and not current_user.is_admin:
            print(f"User {current_user.id} not authorized to edit character {character_id}")
            print(f"Creator from file: {char_data.get('creator')}")
            print(f"Current user: {current_user.id}")
            return redirect(url_for('serve_index'))
            
        print(f"Authorization passed, rendering edit-character.html for character {character_id}")
        # Use render_template to serve from templates directory
        return render_template('edit-character.html')  # Changed this line
        
    except Exception as e:
        print(f"Error rendering edit-character page: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('serve_index'))

@app.route('/characters/<character_id>/data')
@login_required
def get_character_data(character_id):
    try:
        # Define the character JSON file path
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        
        # Check if character JSON exists
        if not os.path.exists(char_file_path):
            return jsonify({'error': 'Character not found'}), 404
            
        # Load character data from JSON
        try:
            with open(char_file_path, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
                
            # Check ownership or admin status
            if str(char_data.get('creator')) != str(current_user.id) and not current_user.is_admin:
                return jsonify({'error': 'Unauthorized'}), 403

            # Check database for additional data
            character = Character.query.get(character_id)
            if character:
                # Merge database data if it exists
                char_data.update({
                    'approval_status': character.approval_status,
                    'is_approved': character.is_approved,
                    'settings': character.settings
                })

            return jsonify(char_data)
            
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for character {character_id}: {str(e)}")
            return jsonify({'error': 'Invalid character data format'}), 500
            
    except Exception as e:
        print(f"Error getting character data: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/edit-character', methods=['GET'])
@login_required
def edit_character_route():
    try:
        response = make_response(render_template('edit-character.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering edit-character page: {str(e)}")
        return redirect(url_for('serve_index'))

@app.route('/my-library', methods=['GET'])
@login_required
def my_library_page():
    try:
        response = make_response(render_template('my-library.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering my-library page: {str(e)}")
        return redirect(url_for('serve_index'))

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(STATIC_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(STATIC_DIR, 'js'), filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(STATIC_DIR, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/characters/<character_id>/update', methods=['POST', 'PUT'])
@login_required
def update_character(character_id):
    try:
        # Load existing character data
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        with open(char_file_path, 'r', encoding='utf-8') as f:
            existing_char_data = json.load(f)
            
        # Check ownership
        if str(existing_char_data.get('creator')) != str(current_user.id) and not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Get update data
        data = request.json
        
        # Preserve avatar and background if not in update data
        if 'avatar' not in data or not data['avatar']:
            data['avatar'] = existing_char_data.get('avatar')
        if 'background' not in data or not data['background']:
            data['background'] = existing_char_data.get('background')

        # Update only the fields that are provided
        for key in data:
            if data[key] is not None:  # Only update if value is provided
                existing_char_data[key] = data[key]
                
        # Preserve unchangeable fields
        existing_char_data['id'] = character_id
        existing_char_data['creator'] = str(existing_char_data.get('creator'))
        existing_char_data['dateAdded'] = existing_char_data.get('dateAdded')
        
        # Save updated data back to file
        with open(char_file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_char_data, f, indent=2)
            
        # Update database record if it exists
        character = Character.query.get(character_id)
        if character:
            if data.get('name'): character.name = data['name']
            if data.get('description'): character.description = data['description']
            if data.get('systemPrompt'): character.system_prompt = data['systemPrompt']
            if data.get('greetings'): character.greetings = data['greetings']
            if data.get('category'): character.category = data['category']
            if data.get('ttsVoice'): character.tts_voice = data['ttsVoice']
            if 'isPrivate' in data: character.is_private = data['isPrivate']
            
            # Update settings
            if not character.settings:
                character.settings = {}
            if data.get('tts_rate') is not None: character.settings['tts_rate'] = data['tts_rate']
            if data.get('rvc_pitch') is not None: character.settings['rvc_pitch'] = data['rvc_pitch']
            if data.get('ai_parameters'): character.settings['ai_parameters'] = data['ai_parameters']
            if data.get('rvc_model'): character.settings['rvc_model'] = data['rvc_model']
            
            db.session.commit()
            
        return jsonify({
            'message': 'Character updated successfully',
            'character_id': character_id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating character: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/characters/<character_id>/clear', methods=['POST'])
@login_required
def clear_character_status(character_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        # Update database
        character = Character.query.get_or_404(character_id)
        character.approval_status = 'pending'
        character.is_approved = False
        
        # Update JSON file
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        if os.path.exists(char_file_path):
            with open(char_file_path, 'r+', encoding='utf-8') as f:
                data = json.load(f)
                data['approvalStatus'] = 'pending'
                data['isApproved'] = False
                # Remove rejection reason if it exists
                if 'rejectionReason' in data:
                    del data['rejectionReason']
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
        
        db.session.commit()
        return jsonify({'message': 'Character status cleared successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin-dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('serve_index'))
    try:
        response = make_response(render_template('admin-dashboard.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering admin dashboard: {str(e)}")
        return redirect(url_for('serve_index'))

@app.route('/characters/<character_id>/delete', methods=['POST'])
@login_required
def delete_character(character_id):
    try:
        # Define base paths
        BASE_PATH = '/root/main'
        MODELS_PATH = '/root/models'
        
        # Define all paths that need to be checked and cleaned
        paths_to_clean = {
            'json_file': os.path.join(BASE_PATH, 'characters', f'{character_id}.json'),
            'avatar': os.path.join(BASE_PATH, 'avatars', f'{character_id}-avatar.png'),
            'character_folder': os.path.join(BASE_PATH, 'characters', character_id),
            'model_folder': os.path.join(MODELS_PATH, character_id)
        }

        # First verify character exists and check ownership
        character = None
        if os.path.exists(paths_to_clean['json_file']):
            try:
                with open(paths_to_clean['json_file'], 'r', encoding='utf-8') as f:
                    char_data = json.load(f)
                    if str(char_data.get('creator')) != str(current_user.id) and not current_user.is_admin:
                        return jsonify({'error': 'Unauthorized'}), 403
            except json.JSONDecodeError as e:
                return jsonify({'error': f'Invalid character file: {str(e)}'}), 400
        else:
            return jsonify({'error': 'Character not found'}), 404

        # Check database record if it exists
        character = Character.query.get(character_id)
        if character and character.creator_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403

        # Delete files and folders
        cleanup_log = []
        cleanup_errors = []

        # 1. Delete JSON file
        if os.path.exists(paths_to_clean['json_file']):
            try:
                os.remove(paths_to_clean['json_file'])
                cleanup_log.append(f"Deleted character file: {paths_to_clean['json_file']}")
            except Exception as e:
                cleanup_errors.append(f"Failed to delete character file: {str(e)}")

        # 2. Delete avatar
        if os.path.exists(paths_to_clean['avatar']):
            try:
                os.remove(paths_to_clean['avatar'])
                cleanup_log.append(f"Deleted avatar: {paths_to_clean['avatar']}")
            except Exception as e:
                cleanup_errors.append(f"Failed to delete avatar: {str(e)}")

        # 3. Delete character folder (contains background)
        if os.path.exists(paths_to_clean['character_folder']):
            try:
                shutil.rmtree(paths_to_clean['character_folder'])
                cleanup_log.append(f"Deleted character folder: {paths_to_clean['character_folder']}")
            except Exception as e:
                cleanup_errors.append(f"Failed to delete character folder: {str(e)}")

        # 4. Delete model folder (contains .pth and .index files)
        if os.path.exists(paths_to_clean['model_folder']):
            try:
                shutil.rmtree(paths_to_clean['model_folder'])
                cleanup_log.append(f"Deleted model folder: {paths_to_clean['model_folder']}")
            except Exception as e:
                cleanup_errors.append(f"Failed to delete model folder: {str(e)}")

        # 5. Delete database record if it exists
        if character:
            try:
                db.session.delete(character)
                db.session.commit()
                cleanup_log.append(f"Deleted database record for character: {character_id}")
            except Exception as e:
                db.session.rollback()
                cleanup_errors.append(f"Failed to delete database record: {str(e)}")

        # Log all operations
        print("Cleanup log:")
        for log in cleanup_log:
            print(f"SUCCESS: {log}")
        if cleanup_errors:
            print("Cleanup errors:")
            for error in cleanup_errors:
                print(f"ERROR: {error}")

        if cleanup_errors:
            return jsonify({
                'message': 'Character deleted with some errors',
                'success_log': cleanup_log,
                'errors': cleanup_errors
            }), 207  # Partial success

        return jsonify({
            'message': 'Character deleted successfully',
            'success_log': cleanup_log
        }), 200

    except Exception as e:
        if 'character' in locals() and character:
            db.session.rollback()
        print(f"Error deleting character: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        user = User.query.get_or_404(user_id)
        data = request.json
        user.is_active = data.get('status', not user.is_active)
        db.session.commit()
        return jsonify({'message': 'User status updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<user_id>/credits', methods=['POST'])
@login_required
def modify_user_credits(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        user = User.query.get_or_404(user_id)
        data = request.json
        amount = data.get('amount', 0)
        
        # Create a transaction record
        transaction = CreditTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type='admin_modification',
            description=f'Admin credit modification'
        )
        
        user.credits = amount  # Set to new amount
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({'message': 'Credits updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users')
@login_required
def get_users():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        users = User.query.all()
        return jsonify([{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'credits': user.credits,
            'is_active': user.is_active
        } for user in users])
    except Exception as e:
        print(f"Error in get_users: {str(e)}")  # Add logging
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/stats')
@login_required
def get_admin_stats():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        # Initialize counters
        stats = {
            'total_characters': 0,
            'pending_characters': 0,
            'approved_characters': 0,
            'rejected_characters': 0,
            'private_characters': 0,
            'public_characters': 0,
            'total_users': 0,
            'total_transactions': 0
        }
        
        # Make sure CHARACTER_FOLDER exists
        if os.path.exists(CHARACTER_FOLDER):
            for filename in os.listdir(CHARACTER_FOLDER):
                if filename.endswith('.json'):
                    try:
                        stats['total_characters'] += 1
                        with open(os.path.join(CHARACTER_FOLDER, filename), 'r', encoding='utf-8') as f:
                            char_data = json.load(f)
                            if char_data.get('isPrivate', False):
                                stats['private_characters'] += 1
                            elif char_data.get('isApproved', False):
                                stats['approved_characters'] += 1
                                stats['public_characters'] += 1
                            elif char_data.get('approvalStatus') == 'pending':
                                stats['pending_characters'] += 1
                            elif char_data.get('approvalStatus') == 'rejected':
                                stats['rejected_characters'] += 1
                    except Exception as e:
                        print(f"Error reading character file {filename}: {str(e)}")
                        continue
        
        # Get user and transaction counts from database
        try:
            stats['total_users'] = User.query.count()
            stats['total_transactions'] = CreditTransaction.query.count()
        except Exception as e:
            print(f"Error getting database counts: {str(e)}")
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error in get_admin_stats: {str(e)}")
        return jsonify({
            'total_characters': 0,
            'pending_characters': 0,
            'approved_characters': 0,
            'rejected_characters': 0,
            'private_characters': 0,
            'public_characters': 0,
            'total_users': 0,
            'total_transactions': 0
        })

@app.after_request
def after_request(response):
    # Allow the request origin
    origin = request.headers.get('Origin', '*')
    response.headers.add('Access-Control-Allow-Origin', origin)
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    # Basic security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/login')
def login_page():
    return render_template('login.html', google_client_id=os.getenv('GOOGLE_CLIENT_ID'))




@app.route('/large-upload/model', methods=['POST'])
@login_required
@cross_origin(supports_credentials=True)
def upload_large_model():
    try:
        if 'modelFile' not in request.files or 'indexFile' not in request.files:
            return jsonify({'error': 'Both model and index files are required'}), 400

        model_file = request.files['modelFile']
        index_file = request.files['indexFile']
        char_id = request.form.get('characterId')

        if not char_id:
            return jsonify({'error': 'Character ID is required'}), 400

        # Create model directory
        model_dir = os.path.join('/root/models', char_id)
        os.makedirs(model_dir, exist_ok=True)

        try:
            # Save files
            model_path = os.path.join(model_dir, f"{char_id}.pth")
            index_path = os.path.join(model_dir, f"{char_id}.index")

            model_file.save(model_path)
            index_file.save(index_path)

            return jsonify({
                'message': 'Model uploaded successfully',
                'character_id': char_id
            })

        except Exception as e:
            # Clean up on failure
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            raise Exception(f"Failed to save model files: {str(e)}")

    except Exception as e:
        print(f"Model upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/register')
def register_page():
    return render_template('register.html', google_client_id=os.getenv('GOOGLE_CLIENT_ID'))

@app.route('/setup-story', methods=['GET'])
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
        return redirect(url_for('serve_index'))

@app.route('/story/sessions')
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

@app.route('/story/<session_id>')
@login_required
def story_chat_page(session_id):
    try:
        # Verify the story session exists and user has access
        story = StorySession.query.get_or_404(session_id)
        
        if story.creator_id != current_user.id:
            return redirect(url_for('serve_index'))
            
        response = make_response(render_template('story-chat.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error rendering story chat page: {str(e)}")
        return redirect(url_for('serve_index'))

@app.route('/story/sessions/<session_id>')
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

@app.route('/v1/story/user-message', methods=['POST'])
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

@app.route('/api/v1/generate/image', methods=['POST'])
@login_required
@require_kobold
def generate_image():
    try:
        response = requests.post(
            f'{KOBOLD_API}/sdapi/v1/txt2img',
            json=request.json,
            timeout=60
        )
        
        if not response.ok:
            return handle_kobold_error(response)

        return jsonify(response.json())

    except requests.Timeout:
        return jsonify({
            'error': 'Image generation timed out'
        }), 504
        
    except Exception as e:
        print(f"Error in image generation: {str(e)}")
        return jsonify({
            'error': 'Failed to generate image',
            'details': str(e)
        }), 500

@app.route('/api/extra/multiplayer/getstory', methods=['POST'])
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
        
@app.route('/api/extra/multiplayer/setstory', methods=['POST'])
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
        
@app.route('/api/v1/story/state', methods=['GET'])
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

@app.route('/api/v1/story/update', methods=['POST'])
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

@app.route('/api/v1/generate', methods=['POST'])
@login_required
@require_kobold
def generate_text():
    try:
        response = requests.post(
            f'{KOBOLD_API}/api/v1/generate',
            json=request.json,
            timeout=30
        )
        
        if not response.ok:
            return handle_kobold_error(response)

        return jsonify(response.json())
    except Exception as e:
        print(f"Error in text generation: {str(e)}")
        return jsonify({
            'error': 'Failed to generate text',
            'details': str(e)
        }), 500
    

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Initialize queue handlers
        setup_queue_handlers(kobold_handler, tts_handler)
        
    print("Starting app on internal port 8081 (external 51069)...")
    app.run(host='0.0.0.0', port=8081, debug=False)