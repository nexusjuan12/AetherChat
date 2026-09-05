"""
Central, environment-driven path/config resolution for AetherChat.

Every path used to be hardcoded to /root/... which only worked on the one
box this was originally deployed to. Everything here reads from an env var
first and falls back to a sane default derived from this file's own
location, so the app can run from any checkout.

Override any of these in your .env (or the real environment) when you need
something other than the default layout.
"""
import os

# The directory this repo is checked out into. Every other default path is
# derived from here, so a fresh clone works out of the box with no env vars
# set at all (aside from secrets, which still belong in .env).
BASE_DIR = os.getenv('APP_BASE_DIR', os.path.dirname(os.path.abspath(__file__)))

ENV_FILE = os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env'))
TEMPLATES_DIR = os.getenv('TEMPLATES_DIR', os.path.join(BASE_DIR, 'templates'))
DB_PATH = os.getenv('DB_PATH', os.path.join(BASE_DIR, 'db', 'users.db'))
MODELS_DIR = os.getenv('MODELS_DIR', os.path.join(BASE_DIR, 'models'))
INPUT_DIR = os.getenv('INPUT_DIR', os.path.join(BASE_DIR, 'input'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', os.path.join(BASE_DIR, 'output'))
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'avatars'))
CHARACTER_FOLDER = os.getenv('CHARACTER_FOLDER', os.path.join(BASE_DIR, 'characters'))

SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN') or None

# Comma-separated list of allowed CORS origins. This repo previously used
# "*" (allow-all) with supports_credentials=True, which is a broken/unsafe
# combination for a login-cookie-based app - browsers will actually reject
# "*" with credentialed requests, and if they didn't, it would mean any
# website could ride a logged-in user's session. Defaults to nothing (same-
# origin only); set this for a home-network deployment.
_origins = os.getenv('CORS_ORIGINS', '')
CORS_ORIGINS = [o.strip() for o in _origins.split(',') if o.strip()]
