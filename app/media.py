"""
TTS, chat completion, image generation, and text generation call sites
(the last two forward directly to koboldcpp's SD/kobold-native API), plus
the audio file serving route and the RVC/edge-tts voice listing endpoint.
Moved out of the original monolithic webserver.py.
"""
import os
import time
import uuid
import traceback
from functools import wraps

import requests
from flask import (
    Blueprint, request, jsonify, make_response, send_file,
)
from flask_login import login_required, current_user

import config
from .extensions import db
from .models import CreditTransaction
from queue_system import request_queue
from model_cache import model_cache

bp = Blueprint('media', __name__)

OUTPUT_DIRECTORY = config.OUTPUT_DIR + os.sep
KOBOLD_API = os.getenv('KOBOLD_API', 'http://127.0.0.1:5000')


def kobold_handler(data):
    """Handle Kobold API requests"""
    try:
        # Your existing Kobold API call
        kobold_response = requests.post(
            f'{KOBOLD_API}/v1/chat/completions',
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

@bp.route('/v1/tts', methods=['POST'])
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

@bp.route('/v1/chat/status/<request_id>')
@login_required
def check_chat_status(request_id):
    status = request_queue.get_status(request_id)
    if not status:
        return jsonify({'error': 'Request not found'}), 404
    return jsonify(status)

@bp.route('/v1/chat/completions', methods=['POST'])
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

@bp.route('/audio/<filename>', methods=['GET'])
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

@bp.route('/api/available-voices', methods=['GET'])
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
        
        models_dir = config.MODELS_DIR
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

def handle_options():
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Content-Length')
    response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '3600')
    return response

@bp.route('/api/v1/generate/image', methods=['POST'])
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

@bp.route('/api/v1/generate', methods=['POST'])
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
