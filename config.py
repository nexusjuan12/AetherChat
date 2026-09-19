"""Environment-driven configuration for AetherChat."""
import os

BASE_DIR = os.getenv('APP_BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env'))
TEMPLATES_DIR = os.getenv('TEMPLATES_DIR', os.path.join(BASE_DIR, 'templates'))
DB_PATH = os.getenv('DB_PATH', os.path.join(BASE_DIR, 'db', 'users.db'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', os.path.join(BASE_DIR, 'output'))
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'avatars'))
CHARACTER_FOLDER = os.getenv('CHARACTER_FOLDER', os.path.join(BASE_DIR, 'characters'))
VOICE_SAMPLE_DIR = os.getenv('VOICE_SAMPLE_DIR', os.path.join(BASE_DIR, 'private', 'voice-samples'))

AUTH_MODE = os.getenv('AUTH_MODE', 'local_invite').strip().lower()
AUTHENTIK_REQUIRED_GROUPS = {
    group.strip().lower()
    for group in os.getenv('AUTHENTIK_REQUIRED_GROUPS', 'members').split(',')
    if group.strip()
}
TRUST_AUTHENTIK_HEADERS = os.getenv('TRUST_AUTHENTIK_HEADERS', 'false').lower() == 'true'

SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN') or None
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true'
_origins = os.getenv('CORS_ORIGINS', '')
CORS_ORIGINS = [origin.strip() for origin in _origins.split(',') if origin.strip()]

LLM_API_BASE = os.getenv('LLM_API_BASE', 'http://127.0.0.1:5000').rstrip('/')
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
TTS_API_BASE = os.getenv('TTS_API_BASE', 'http://127.0.0.1:8000').rstrip('/')
TTS_API_KEY = os.getenv('TTS_API_KEY', '')
TTS_ACCELERATOR_CONTROLLER_URL = os.getenv('TTS_ACCELERATOR_CONTROLLER_URL', '').rstrip('/')
TTS_DEFAULT_VOICE = os.getenv('TTS_DEFAULT_VOICE', 'default')

VIDEO_ENABLED_DEFAULT = os.getenv('VIDEO_ENABLED_DEFAULT', 'false').lower() == 'true'
STORY_ENABLED_DEFAULT = os.getenv('STORY_ENABLED_DEFAULT', 'false').lower() == 'true'
