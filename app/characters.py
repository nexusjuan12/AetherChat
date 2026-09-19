"""
Character CRUD, approval workflow, and avatar/background/model uploads.
Moved out of the original monolithic webserver.py.
"""
import os
import json
import shutil
import re
import uuid
from datetime import datetime

from flask import (
    Blueprint, request, jsonify, redirect, url_for, render_template,
    make_response,
)
from flask_login import login_required, current_user

import config
from .extensions import db
from .models import Character, CharacterApprovalQueue, VoiceProfile

bp = Blueprint('characters', __name__)

UPLOAD_FOLDER = config.UPLOAD_FOLDER
CHARACTER_FOLDER = config.CHARACTER_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'wmv'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

CHARACTER_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,100}$')

def resolve_character_id_for_upload(char_id):
    """
    Validate a character id used to build a filesystem path for an
    avatar/background/model upload.

    Character creation uploads avatar/background/model files *before* the
    Character row exists, so a char_id with no matching row yet is
    legitimate and allowed through. A char_id that already belongs to a
    *different* user's character is rejected - that's the case that let any
    logged-in user overwrite another user's files.

    Returns (char_id, None) if the upload may proceed, or
    (None, (response, status_code)) if it must be rejected.
    """
    if not char_id or not CHARACTER_ID_PATTERN.match(char_id):
        return None, (jsonify({'error': 'Invalid character ID'}), 400)

    existing = Character.query.get(char_id)
    if existing and str(existing.creator_id) != str(current_user.id) and not current_user.is_admin:
        return None, (jsonify({'error': 'You do not have permission to modify this character'}), 403)

    return char_id, None

@bp.route('/create-character', methods=['GET', 'POST'])
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
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/characters/create', methods=['POST'])
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
        voice_profile_id = data.get('voice_profile_id')
        if voice_profile_id:
            voice_profile = db.session.get(VoiceProfile, voice_profile_id)
            if not voice_profile or not voice_profile.is_usable_by(current_user):
                return jsonify({'error': 'Selected voice profile is unavailable'}), 403

        settings = {
            'tts_rate': data.get('tts_rate', 0),
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
            voice_profile_id=voice_profile_id,
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
                'voice_profile_id': voice_profile_id,
                'dateAdded': datetime.utcnow().isoformat(),
                'creator': current_user.id,
                'isPrivate': is_private,
                'isApproved': is_private,
                'approvalStatus': 'approved' if is_private else 'pending',
                'ai_parameters': ai_parameters
            }
            
            if data.get('background'):
                char_file_data['background'] = data['background']

            # Save character JSON file
            char_file_path = os.path.join(CHARACTER_FOLDER, f"{char_id}.json")
            with open(char_file_path, 'w', encoding='utf-8') as f:
                json.dump(char_file_data, f, indent=2)
            print("Character JSON file created")
            
            db.session.commit()
            print("Database committed")
            
            return jsonify({
                'message': 'Character created successfully',
                'character_id': char_id,
                'approval_status': 'approved' if is_private else 'pending'
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

@bp.route('/characters/public')
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

@bp.route('/characters/private')
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

@bp.route('/admin/characters/pending')
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

@bp.route('/admin/characters/<character_id>/approve', methods=['POST'])
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
            
            db.session.commit()

        return jsonify({'message': 'Character approved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/characters/<character_id>/reject', methods=['POST'])
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

@bp.route('/upload/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
        
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    if file and allowed_file(file.filename):
        # The frontend sends characterId as a form field. Previously this
        # was ignored in favor of parsing it out of the *filename* itself
        # (file.filename.split('-')[0]) with no sanitization at all, which
        # let a crafted filename like "../../etc/x-avatar.png" write outside
        # UPLOAD_FOLDER entirely.
        character_id, error = resolve_character_id_for_upload(request.form.get('characterId'))
        if error:
            return error

        filename = f"{character_id}-avatar.png"  # Use character ID consistently
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return jsonify({'avatarPath': f'./avatars/{filename}'}), 200

    return jsonify({'error': 'Invalid file type'}), 400

@bp.route('/upload/character-background', methods=['POST'])
@login_required
def upload_background():
    if 'background' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['background']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        # Get character ID from form data. Previously used with no
        # validation at all - any authenticated user could pass another
        # user's characterId (broken access control) or a value containing
        # ".." (path traversal) to write into an arbitrary directory.
        character_id, error = resolve_character_id_for_upload(request.form.get('characterId'))
        if error:
            return error

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

@bp.route('/check-character/<character_name>')
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

@bp.route('/characters/upload-model', methods=['POST'])
@login_required
def upload_model():
    return jsonify({
        'error': 'RVC model uploads are no longer supported. Create a Qwen voice profile instead.'
    }), 410

@bp.route('/characters/submit-for-review/<character_id>', methods=['POST'])
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

@bp.route('/characters/my-library')
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

@bp.route('/edit-character/<character_id>')
@login_required
def edit_character_page(character_id):
    try:
        print(f"Attempting to edit character: {character_id}")
        # Load the character data from JSON
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        print(f"Looking for character file at: {char_file_path}")
        
        if not os.path.exists(char_file_path):
            print(f"Character file not found: {char_file_path}")
            return redirect(url_for('static_routes.serve_index'))
            
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
            return redirect(url_for('static_routes.serve_index'))
            
        print(f"Authorization passed, rendering edit-character.html for character {character_id}")
        # Use render_template to serve from templates directory
        return render_template('edit-character.html')  # Changed this line
        
    except Exception as e:
        print(f"Error rendering edit-character page: {str(e)}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/characters/<character_id>/data')
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

@bp.route('/edit-character', methods=['GET'])
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
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/my-library', methods=['GET'])
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
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/characters/<character_id>/update', methods=['POST', 'PUT'])
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
            if data.get('ai_parameters'): character.settings['ai_parameters'] = data['ai_parameters']
            if 'voice_profile_id' in data:
                voice_profile_id = data.get('voice_profile_id') or None
                if voice_profile_id:
                    voice_profile = db.session.get(VoiceProfile, voice_profile_id)
                    if not voice_profile or not voice_profile.is_usable_by(current_user):
                        return jsonify({'error': 'Selected voice profile is unavailable'}), 403
                character.voice_profile_id = voice_profile_id
            
            db.session.commit()
            
        return jsonify({
            'message': 'Character updated successfully',
            'character_id': character_id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating character: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/characters/<character_id>/clear', methods=['POST'])
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

@bp.route('/characters/<character_id>/delete', methods=['POST'])
@login_required
def delete_character(character_id):
    try:
        # Define base paths
        BASE_PATH = config.BASE_DIR
        
        # Define all paths that need to be checked and cleaned
        paths_to_clean = {
            'json_file': os.path.join(BASE_PATH, 'characters', f'{character_id}.json'),
            'avatar': os.path.join(BASE_PATH, 'avatars', f'{character_id}-avatar.png'),
            'character_folder': os.path.join(BASE_PATH, 'characters', character_id)
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

        # 4. Delete database record if it exists
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

@bp.route('/large-upload/model', methods=['POST'])
@login_required
def upload_large_model():
    return jsonify({
        'error': 'RVC model uploads are no longer supported. Create a Qwen voice profile instead.'
    }), 410
