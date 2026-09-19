"""Text, speech, voice-profile, and legacy image-provider routes."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import requests
from flask import Blueprint, abort, jsonify, render_template, request, send_file
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

import config
from .extensions import db
from .models import VoiceProfile
from .providers import LlmClient, ProviderError, SpeechClient, write_owned_audio
from queue_system import request_queue

bp = Blueprint('media', __name__)
KOBOLD_API = os.getenv('KOBOLD_API', '').rstrip('/')
ALLOWED_VOICE_EXTENSIONS = {'wav', 'mp3', 'ogg', 'flac'}


def kobold_handler(_user_id: str, data: dict) -> dict:
    return LlmClient().complete(data)


def _voice_profile_for_request(data: dict) -> str | None:
    profile_id = data.get('voice_profile_id')
    if not profile_id:
        return None
    profile = db.session.get(VoiceProfile, profile_id)
    if not profile or not profile.is_usable_by(current_user) or not profile.provider_profile_id:
        raise ProviderError('Selected voice profile is unavailable')
    return profile.provider_profile_id


def tts_handler(user_id: str, data: dict) -> dict:
    text = str(data.get('text', '')).strip()
    if not text or len(text) > 4000:
        raise ProviderError('Speech text must be between 1 and 4000 characters')
    # The owning request has already been authenticated. Profile access is
    # rechecked by the route before this background job is queued.
    audio = SpeechClient().synthesize(text, data.get('provider_voice_profile_id'))
    filename, _path = write_owned_audio(user_id, audio)
    return {'audio_url': f'/audio/{filename}'}


def _submit_job(kind: str, data: dict):
    if kind == 'tts':
        data['provider_voice_profile_id'] = _voice_profile_for_request(data)
    try:
        request_id = request_queue.add_request(current_user.id, kind, data)
    except ValueError:
        return jsonify({'error': 'Service is not configured'}), 503
    return jsonify({'status': 'queued', 'request_id': request_id}), 202


@bp.route('/v1/chat/completions', methods=['POST'])
@login_required
def chat_completions():
    return _submit_job('chat', request.get_json(silent=True) or {})


@bp.route('/v1/tts', methods=['POST'])
@login_required
def tts():
    return _submit_job('tts', request.get_json(silent=True) or {})


@bp.route('/v1/jobs/<request_id>')
@login_required
def job_status(request_id):
    status = request_queue.get_status(request_id, current_user.id)
    if not status:
        return jsonify({'error': 'Request not found'}), 404
    return jsonify(status)


@bp.route('/audio/<filename>')
@login_required
def get_audio(filename):
    filename = os.path.basename(filename)
    if not filename.startswith(f'{current_user.id}-'):
        abort(404)
    path = Path(config.OUTPUT_DIR) / filename
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype='audio/wav', conditional=True)


@bp.route('/api/voice-profiles')
@login_required
def voice_profiles():
    profiles = VoiceProfile.query.filter(
        (VoiceProfile.owner_id == current_user.id) |
        ((VoiceProfile.visibility == 'public') & (VoiceProfile.approval_status == 'approved'))
    ).order_by(VoiceProfile.display_name).all()
    return jsonify([profile.to_dict() for profile in profiles if profile.is_usable_by(current_user)])


@bp.route('/voice-profiles')
@login_required
def voice_profiles_page():
    return render_template('voice-profiles.html')


@bp.route('/api/voice-profiles', methods=['POST'])
@login_required
def create_voice_profile():
    sample = request.files.get('sample')
    display_name = str(request.form.get('display_name', '')).strip()
    reference_text = str(request.form.get('reference_text', '')).strip()
    visibility = str(request.form.get('visibility', 'private')).strip().lower()
    consent = request.form.get('consent') == 'true'
    if not sample or not display_name or not reference_text or not consent:
        return jsonify({'error': 'Sample, name, transcript, and consent are required'}), 400
    if visibility not in {'private', 'public'}:
        return jsonify({'error': 'Invalid visibility'}), 400
    suffix = Path(secure_filename(sample.filename)).suffix.lower().lstrip('.')
    if suffix not in ALLOWED_VOICE_EXTENSIONS:
        return jsonify({'error': 'Unsupported voice sample format'}), 400
    profile = VoiceProfile(
        id=str(uuid.uuid4()), owner_id=current_user.id, display_name=display_name, sample_path='',
        reference_text=reference_text, visibility=visibility,
        approval_status='pending' if visibility == 'public' else 'approved',
    )
    path = Path(config.VOICE_SAMPLE_DIR) / f'{profile.id}.{suffix}'
    path.parent.mkdir(parents=True, exist_ok=True)
    sample.save(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        path.unlink(missing_ok=True)
        return jsonify({'error': 'Voice sample exceeds 25 MB'}), 413
    profile.sample_path = path.name
    try:
        profile.provider_profile_id = SpeechClient().prepare_voice_profile(path, reference_text, display_name)
    except ProviderError as error:
        path.unlink(missing_ok=True)
        return jsonify({'error': str(error)}), 503
    db.session.add(profile)
    db.session.commit()
    return jsonify(profile.to_dict()), 201


@bp.route('/api/voice-profiles/<profile_id>/approve', methods=['POST'])
@login_required
def approve_voice_profile(profile_id):
    if not current_user.is_admin:
        abort(403)
    profile = db.session.get(VoiceProfile, profile_id)
    if not profile or profile.visibility != 'public':
        abort(404)
    profile.approval_status = 'approved'
    profile.reviewed_by = current_user.id
    db.session.commit()
    return jsonify(profile.to_dict())


@bp.route('/api/admin/voice-profiles/pending')
@login_required
def pending_voice_profiles():
    if not current_user.is_admin:
        abort(403)
    profiles = VoiceProfile.query.filter_by(visibility='public', approval_status='pending').order_by(VoiceProfile.created_at).all()
    return jsonify([profile.to_dict() for profile in profiles])


@bp.route('/api/voice-profiles/<profile_id>', methods=['DELETE'])
@login_required
def disable_voice_profile(profile_id):
    profile = db.session.get(VoiceProfile, profile_id)
    if not profile or (profile.owner_id != current_user.id and not current_user.is_admin):
        abort(404)
    if profile.provider_profile_id:
        try:
            SpeechClient().delete_voice_profile(profile.provider_profile_id)
        except ProviderError as error:
            return jsonify({'error': str(error)}), 503
    profile.disabled_at = db.func.now()
    db.session.commit()
    return '', 204


@bp.route('/api/v1/generate/image', methods=['POST'])
@login_required
def generate_image():
    if not KOBOLD_API:
        return jsonify({'error': 'Legacy image provider is not configured'}), 503
    try:
        response = requests.post(f'{KOBOLD_API}/sdapi/v1/txt2img', json=request.get_json(), timeout=120)
        return (response.content, response.status_code, {'Content-Type': response.headers.get('Content-Type', 'application/json')})
    except requests.RequestException:
        return jsonify({'error': 'Legacy image provider is unavailable'}), 503
