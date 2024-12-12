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
from main.email_service import send_verification_email
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


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
            "origins": [
                "http://yourwaifai.uk",
                "https://yourwaifai.uk",
                "http://www.yourwaifai.uk",
                "https://www.yourwaifai.uk"
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    }
)

# App Configuration
app.config.update(
    SQLALCHEMY_DATABASE_URI='sqlite:////root/db/users.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-key-change-this'),
    STATIC_FOLDER='/root/main',
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=31),  
    SESSION_COOKIE_DOMAIN='yourwaifai.uk',  
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
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True)
    verification_token_expires = db.Column(db.DateTime)
    
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
        
    # Generate verification token
    verification_token = str(uuid.uuid4())
    token_expiry = datetime.utcnow() + timedelta(hours=24)
    
    user = User(
        email=data['email'],
        username=data.get('username', data['email'].split('@')[0]),
        verification_token=verification_token,
        verification_token_expires=token_expiry,
        email_verified=False,
        created_at=datetime.utcnow()
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.flush()  # Get user ID without committing
        
        # Send verification email
        if send_verification_email(user.email, verification_token):
            db.session.commit()
            return jsonify({
                'message': 'Registration successful. Please check your email to verify your account.',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'credits': user.credits
                }
            }), 201
        else:
            db.session.rollback()
            return jsonify({'error': 'Failed to send verification email'}), 500
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
        
@app.route('/auth/google', methods=['GET', 'POST'])
def google_auth():
    if request.method == 'GET':
        # Redirect to Google OAuth login page
        return redirect(f'https://accounts.google.com/o/oauth2/v2/auth?' + 
            f'client_id={os.getenv("GOOGLE_CLIENT_ID")}&' +
            'response_type=code&' +
            f'redirect_uri={os.getenv("GOOGLE_REDIRECT_URI")}&' +
            'scope=email profile&' +
            'access_type=offline')
    
    # POST request handling (existing code)
    try:
        token = request.json.get('token')
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            os.getenv('GOOGLE_CLIENT_ID')
        )

        email = idinfo['email']
        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(
                email=email,
                username=idinfo.get('name', email.split('@')[0]),
                google_id=idinfo['sub'],
                email_verified=True
            )
            db.session.add(user)
            db.session.commit()

        login_user(user, remember=True)
        session.permanent = True

        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'credits': user.credits
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Add OAuth callback route
@app.route('/auth/google/callback')
def google_callback():
    try:
        code = request.args.get('code')
        token_response = requests.post('https://oauth2.googleapis.com/token', data={
            'code': code,
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI'),
            'grant_type': 'authorization_code'
        })

        token_data = token_response.json()
        id_token_info = id_token.verify_oauth2_token(
            token_data['id_token'],
            google_requests.Request(),
            os.getenv('GOOGLE_CLIENT_ID')
        )

        email = id_token_info['email']
        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(
                email=email,
                username=id_token_info.get('name', email.split('@')[0]),
                google_id=id_token_info['sub'],
                email_verified=True
            )
            db.session.add(user)
            db.session.commit()

        login_user(user, remember=True)
        session.permanent = True

        return redirect('/')

    except Exception as e:
        print(f"Google callback error: {str(e)}")
        return redirect('/login?error=google_auth_failed')

@app.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        return render_template('verification_error.html', 
                             message="Invalid verification token"), 404
                             
    if user.email_verified:
        return render_template('verification_error.html', 
                             message="Email already verified"), 400
                             
    if user.verification_token_expires < datetime.utcnow():
        return render_template('verification_error.html', 
                             message="Verification token has expired"), 400
    
    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.session.commit()
    
    return render_template('verification_success.html')

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing credentials'}), 400
        
    user = User.query.filter_by(email=data['email']).first()
    
    if user and user.check_password(data['password']):
        # Check if email is verified for non-Google accounts
        if not user.google_id and not user.email_verified:
            return jsonify({'error': 'Please verify your email before logging in'}), 403
            
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

        
@app.route('/v1/tts', methods=['POST', 'OPTIONS'])
@login_required
def tts():
    if request.method == 'OPTIONS':
        return handle_options()

    try:
        # Add credit handling
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

        # Your existing working code
        data = request.json
        text = data.get("text")
        character_id = data.get("rvc_model") or data.get("id")  # Try rvc_model first, fallback to id
        edge_voice = data.get("edge_voice")
        tts_rate = data.get("tts_rate", 0)
        rvc_pitch = data.get("rvc_pitch", 0)

        print(f"Processing TTS request for character: {character_id}")

        if not text or not character_id or not edge_voice:
            current_user.add_credits(CREDITS_PER_TTS)  # Refund credits
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({"error": "Text, character_id, and edge_voice are required"}), 400

        # Try both possible model locations
        model_paths = [
            f"/root/models/{character_id}/{character_id}.pth",  # Original location
            f"/root/models/melon/melon.pth" if character_id == "bigfoot" else None  # Special case for bigfoot
        ]
        
        index_paths = [
            f"/root/models/{character_id}/{character_id}.index",  # Original location
            f"/root/models/melon/melon.index" if character_id == "bigfoot" else None  # Special case for bigfoot
        ]

        # Find first valid model/index pair
        model_path = None
        index_path = None
        for m_path, i_path in zip(model_paths, index_paths):
            if m_path and i_path and os.path.exists(m_path) and os.path.exists(i_path):
                model_path = m_path
                index_path = i_path
                break

        if not model_path or not index_path:
            current_user.add_credits(CREDITS_PER_TTS)  # Refund credits
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({"error": f"Voice model files not found for {character_id}"}), 404

        unique_id = str(uuid.uuid4())
        output_filename = f"response_{unique_id}.wav"
        output_path = os.path.join(OUTPUT_DIRECTORY, output_filename)

        try:
            print(f"Using model: {model_path}")
            print(f"Using index: {index_path}")
            
            tts = TTS_RVC(
                rvc_path="src/rvclib",
                model_path=model_path,
                input_directory="/root/input/",
                index_path=index_path
            )
            
            tts.set_voice(edge_voice)
            
            # Call TTS directly with parentheses
            tts(
                text=text,
                pitch=rvc_pitch,
                tts_rate=tts_rate,
                output_filename=output_path
            )

            if not os.path.exists(output_path):
                current_user.add_credits(CREDITS_PER_TTS)  # Refund credits
                db.session.delete(transaction)
                db.session.commit()
                return jsonify({"error": "Failed to generate audio file"}), 500

            db.session.commit()  # Commit the transaction if successful
            return jsonify({"audio_url": f"/audio/{output_filename}"}), 200

        except Exception as e:
            current_user.add_credits(CREDITS_PER_TTS)  # Refund credits
            db.session.delete(transaction)
            db.session.commit()
            print(f"Error in TTS generation: {str(e)}")
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        if 'transaction' in locals():  # Only refund if transaction was created
            current_user.add_credits(CREDITS_PER_TTS)
            db.session.delete(transaction)
            db.session.commit()
        print(f"TTS Error: {str(e)}")
        return jsonify({"error": str(e)}), 500



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
        # Update database
        character = Character.query.get_or_404(character_id)
        character.is_approved = True
        character.approval_status = 'approved'
        
        # Update JSON file
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        if os.path.exists(char_file_path):
            with open(char_file_path, 'r+', encoding='utf-8') as f:
                data = json.load(f)
                data['isApproved'] = True
                data['approvalStatus'] = 'approved'
                if 'rejectionReason' in data:
                    del data['rejectionReason']
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
        
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
        # Get character ID from form data - use as-is since it's already sanitized
        character_id = request.form.get('characterId')
        
        # Create character directory
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
        all_characters = []
        CHARACTER_FOLDER = '/root/main/characters'  # Make sure this path matches your setup
        
        # Read all character JSON files
        for filename in os.listdir(CHARACTER_FOLDER):
            if filename.endswith('.json'):
                file_path = os.path.join(CHARACTER_FOLDER, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        char_data = json.load(f)
                        # Add the character ID from filename if not present
                        if 'id' not in char_data:
                            char_data['id'] = filename.replace('.json', '')
                        all_characters.append(char_data)
                except Exception as e:
                    print(f"Error reading character file {filename}: {e}")
                    continue

        # Filter characters based on user access
        response_data = {
            'private': [],
            'public': [],
            'pending': []
        }

        for char in all_characters:
            # For admin, show all characters
            if current_user.is_admin:
                if char.get('isPrivate', False):
                    response_data['private'].append(char)
                elif char.get('approvalStatus') == 'pending':
                    response_data['pending'].append(char)
                else:
                    response_data['public'].append(char)
            # For regular users, show only their characters
            elif char.get('creator') == current_user.id:
                if char.get('isPrivate', False):
                    response_data['private'].append(char)
                elif char.get('approvalStatus') == 'pending':
                    response_data['pending'].append(char)
                elif char.get('isApproved', False):
                    response_data['public'].append(char)

        print(f"Found {len(all_characters)} total characters")
        print(f"Returning: {len(response_data['private'])} private, "
              f"{len(response_data['public'])} public, "
              f"{len(response_data['pending'])} pending")
        
        return jsonify(response_data)

    except Exception as e:
        print(f"Error in my_library: {str(e)}")
        import traceback
        traceback.print_exc()
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
        character = Character.query.get_or_404(character_id)
        
        # Check ownership
        if character.creator_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Get character JSON data
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        with open(char_file_path, 'r', encoding='utf-8') as f:
            char_data = json.load(f)
            
        return jsonify(char_data)
        
    except Exception as e:
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

@app.route('/delete-character/<character_id>', methods=['POST'])
@login_required
def delete_character(character_id):
    try:
        # First check if character exists in database
        character = Character.query.get_or_404(character_id)
        
        # Check if user is authorized to delete
        if character.creator_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Delete all associated files
        cleanup_successful = True
        error_messages = []
        
        # 1. Delete JSON file
        char_file_path = os.path.join(CHARACTER_FOLDER, f"{character_id}.json")
        try:
            if os.path.exists(char_file_path):
                os.remove(char_file_path)
                print(f"Deleted JSON file: {char_file_path}")
        except Exception as e:
            cleanup_successful = False
            error_messages.append(f"Failed to delete JSON file: {str(e)}")

        # 2. Delete avatar
        avatar_path = os.path.join(UPLOAD_FOLDER, f"{character_id}-avatar.png")
        try:
            if os.path.exists(avatar_path):
                os.remove(avatar_path)
                print(f"Deleted avatar: {avatar_path}")
        except Exception as e:
            cleanup_successful = False
            error_messages.append(f"Failed to delete avatar: {str(e)}")

        # 3. Delete character directory (contains backgrounds, etc)
        char_dir = os.path.join(CHARACTER_FOLDER, character_id)
        try:
            if os.path.exists(char_dir):
                shutil.rmtree(char_dir)
                print(f"Deleted character directory: {char_dir}")
        except Exception as e:
            cleanup_successful = False
            error_messages.append(f"Failed to delete character directory: {str(e)}")

        # 4. Delete voice model directory
        model_dir = os.path.join('/root/models', character_id)
        try:
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
                print(f"Deleted model directory: {model_dir}")
        except Exception as e:
            cleanup_successful = False
            error_messages.append(f"Failed to delete model directory: {str(e)}")

        # 5. Delete from database
        try:
            db.session.delete(character)
            db.session.commit()
            print(f"Deleted character from database: {character_id}")
        except Exception as e:
            db.session.rollback()
            cleanup_successful = False
            error_messages.append(f"Failed to delete from database: {str(e)}")

        if not cleanup_successful:
            return jsonify({
                'message': 'Character deleted with some errors',
                'errors': error_messages
            }), 207  # 207 Multi-Status
            
        return jsonify({
            'message': 'Character and all associated files deleted successfully'
        }), 200
        
    except Exception as e:
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
    origin = request.headers.get('Origin', '')
    allowed_origins = [
        'https://yourwaifai.uk',
        'https://www.yourwaifai.uk',
        'http://136.38.129.228:51069'  # Keep during testing
    ]
    
    if origin in allowed_origins:
        response.headers.add('Access-Control-Allow-Origin', origin)
    
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    # Add security headers
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


# Initialize database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("Starting app on internal port 8081 (external 51069)...")
    app.run(host='0.0.0.0', port=8081, debug=False)