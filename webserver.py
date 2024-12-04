import zipfile  # built-in
import py7zr
import rarfile
import tempfile
import os
import shutil
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, make_response
from datetime import timedelta
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

# Load environment variables
load_dotenv('/root/.env')

app = Flask(__name__,
    template_folder='/root/templates',
    static_folder='/root/main'
)
CORS(app, supports_credentials=True)

# App Configuration
app.config.update(
    SQLALCHEMY_DATABASE_URI='sqlite:////root/db/users.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-key-change-this'),
    STATIC_FOLDER='/root/main',
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=31),  
    SESSION_COOKIE_DOMAIN=None,  
    SESSION_COOKIE_PATH='/'  
)

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
    google_id = db.Column(db.String(200), unique=True)
    characters = db.relationship('Character', backref='creator', lazy=True)
    
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
        
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Authentication Routes
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
        
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 409
        
    user = User(
        email=data['email'],
        username=data.get('username', data['email'].split('@')[0])
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'credits': user.credits
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing credentials'}), 400
        
    user = User.query.filter_by(email=data['email']).first()
    
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
                'credits': user.credits
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
            'credits': current_user.credits
        }
    }), 200

# Static Routes
@app.route('/')
def serve_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory(STATIC_DIR, path)
    except Exception as e:
        print(f"Error serving {path}: {e}")
        return f"Error: Could not serve {path}", 404

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
@login_required
def chat_completions():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        # Check if user has enough credits
        CREDITS_PER_MESSAGE = 10
        
        if not current_user.deduct_credits(CREDITS_PER_MESSAGE):
            return jsonify({'error': 'Insufficient credits'}), 402
            
        # Log the transaction
        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-CREDITS_PER_MESSAGE,
            transaction_type='message',
            description='Chat completion message'
        )
        db.session.add(transaction)
        
        data = request.json
        print(f"Forwarding chat request to Kobold: {data}")
        kobold_response = requests.post('http://127.0.0.1:5000/v1/chat/completions', json=data)
        
        if not kobold_response.ok:
            # Refund credits if API call fails
            current_user.add_credits(CREDITS_PER_MESSAGE)
            db.session.delete(transaction)
            db.session.commit()
            print(f"Kobold API error: {kobold_response.status_code} - {kobold_response.text}")
            raise Exception(f"Kobold API error: {kobold_response.status_code}")
            
        db.session.commit()
        return jsonify(kobold_response.json())
        
    except Exception as e:
        db.session.rollback()
        print(f"Chat Error: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
def cleanup_old_files(keep_last=10):
    """
    Cleanup old audio files, keeping the most recent ones
    Args:
        keep_last (int): Number of recent files to keep
    """
    try:
        # Get all .wav files in the output directory
        files = [f for f in os.listdir(OUTPUT_DIRECTORY) if f.endswith('.wav')]
        # Sort files by modification time, newest first
        files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIRECTORY, x)), reverse=True)
        
        # Remove all but the keep_last most recent files
        for f in files[keep_last:]:
            try:
                os.remove(os.path.join(OUTPUT_DIRECTORY, f))
            except Exception as e:
                print(f"Error removing file {f}: {e}")
                
    except Exception as e:
        print(f"Error during cleanup: {e}")

@app.route('/v1/tts', methods=['POST', 'OPTIONS'])
@login_required
def tts():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        CREDITS_PER_TTS = 5
        if not current_user.deduct_credits(CREDITS_PER_TTS):
            return jsonify({'error': 'Insufficient credits'}), 402

        transaction = CreditTransaction(
            user_id=current_user.id,
            amount=-CREDITS_PER_TTS,
            transaction_type='tts',
            description='Text-to-speech conversion'
        )
        db.session.add(transaction)

        data = request.json
        text = data.get("text")
        rvc_model = data.get("rvc_model")
        edge_voice = data.get("edge_voice")
        tts_rate = data.get("tts_rate", 0)
        rvc_pitch = data.get("rvc_pitch", 0)

        if not text or not rvc_model or not edge_voice:
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({"error": "Text, rvc_model, and edge_voice are required"}), 400

        unique_id = str(uuid.uuid4())
        output_filename = f"response_{unique_id}.wav"
        output_path = os.path.join(OUTPUT_DIRECTORY, output_filename)

        cleanup_old_files()

        model_path = f"/root/models/{rvc_model}/{rvc_model}.pth"
        index_path = f"/root/models/{rvc_model}/{rvc_model}.index"

        if not os.path.exists(model_path) or not os.path.exists(index_path):
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({"error": f"Model or index file not found for {rvc_model}"}), 404

        try:
            tts = TTS_RVC(
                rvc_path="src/rvclib",
                model_path=model_path,
                input_directory="/root/input/",
                index_path=index_path
            )
            
            tts.set_voice(edge_voice)

            tts(
                text=text,
                pitch=rvc_pitch,
                tts_rate=tts_rate,
                output_filename=output_path
            )

            if not os.path.exists(output_path):
                current_user.add_credits(CREDITS_PER_TTS)
                db.session.delete(transaction)
                db.session.commit()
                return jsonify({"error": "Failed to generate audio file"}), 500

            db.session.commit()
            if output_filename in request.headers.get('Current-Audio', ''):
                return jsonify({"message": "Audio already playing"}), 200
            return jsonify({"audio_url": f"/audio/{output_filename}"}), 200
        
        except Exception as e:
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({"error": f"TTS processing failed: {str(e)}"}), 500

    except Exception as e:
        if 'transaction' in locals():
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
        return jsonify({"error": str(e)}), 500


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
        characters = Character.query.filter_by(is_private=False, is_approved=True).all()
        return jsonify([{
            'id': char.id,
            'name': char.name,
            'description': char.description,
            'avatar': char.avatar,
            'category': char.category
        } for char in characters])
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
        pending = Character.query.filter_by(
            is_private=False,
            is_approved=False,
            approval_status='pending'
        ).all()
        return jsonify([{
            'id': char.id,
            'name': char.name,
            'description': char.description,
            'avatar': char.avatar,
            'category': char.category,
            'creator_id': char.creator_id
        } for char in pending])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/characters/<character_id>/approve', methods=['POST'])
@login_required
def approve_character(character_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        character = Character.query.get_or_404(character_id)
        character.is_approved = True
        character.approval_status = 'approved'
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
        character = Character.query.get_or_404(character_id)
        character.approval_status = 'rejected'
        character.rejection_reason = data.get('reason', '')
        db.session.commit()
        return jsonify({'message': 'Character rejected'})
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
        # Get character ID for consistency
        character_id = file.filename.split('-')[0]
        
        # Create character directory using ID
        char_dir = os.path.join(CHARACTER_FOLDER, character_id)
        os.makedirs(char_dir, exist_ok=True)
        
        # Save file with original extension
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
        # Handle image fallback
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
        if 'modelFile' not in request.files or 'indexFile' not in request.files:
            return jsonify({'error': 'Both model and index files are required'}), 400

        model_file = request.files['modelFile']
        index_file = request.files['indexFile']
        char_id = request.form.get('characterId')

        if not char_id:
            return jsonify({'error': 'Character ID is required'}), 400

        if not model_file.filename.endswith('.pth') or not index_file.filename.endswith('.index'):
            return jsonify({'error': 'Invalid file types. Need .pth and .index files'}), 400

        # Create model directory using character ID
        model_dir = os.path.join('/root/models', char_id)
        os.makedirs(model_dir, exist_ok=True)

        # Save files with character ID as the name
        model_path = os.path.join(model_dir, f"{char_id}.pth")
        index_path = os.path.join(model_dir, f"{char_id}.index")

        model_file.save(model_path)
        index_file.save(index_path)

        # Update character record with model info
        character = Character.query.get_or_404(char_id)
        if character.creator_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Update character settings with model info
        character.settings = {
            **character.settings,
            'rvc_model': char_id  # Use character ID as model name
        }

        # Update character JSON file
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{char_id}.json")
        with open(char_file_path, 'r+', encoding='utf-8') as f:
            char_data = json.load(f)
            char_data['rvc_model'] = char_id
            f.seek(0)
            json.dump(char_data, f, indent=2)
            f.truncate()

        db.session.commit()

        return jsonify({
            'message': 'Model uploaded successfully',
            'character_id': char_id
        })

    except Exception as e:
        db.session.rollback()
        if 'model_dir' in locals() and os.path.exists(model_dir):
            shutil.rmtree(model_dir)  # Clean up on failure
        return jsonify({'error': str(e)}), 500

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
@login_required
def my_library():
    try:
        characters = Character.query.filter_by(creator_id=current_user.id).all()
        pending_reviews = CharacterApprovalQueue.query.filter(
            CharacterApprovalQueue.character_id.in_([c.id for c in characters]),
            CharacterApprovalQueue.status == 'pending'
        ).all()
        
        pending_ids = [r.character_id for r in pending_reviews]
        
        return jsonify({
            'private': [c.to_dict() for c in characters if c.is_private],
            'public': [c.to_dict() for c in characters if not c.is_private and c.is_approved],
            'pending': [c.to_dict() for c in characters if c.id in pending_ids]
        })
        
    except Exception as e:
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

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("Starting app on internal port 8081 (external 51069)...")
    app.run(host='0.0.0.0', port=8081, debug=False)