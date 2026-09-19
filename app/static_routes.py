"""
Static file serving (SPA index, css/js/chat assets, favicon) and the two
static legal pages. Moved out of the original monolithic webserver.py.
"""
import os
from pathlib import PurePosixPath

from flask import Blueprint, abort, send_from_directory, render_template

import config

bp = Blueprint('static_routes', __name__)

STATIC_DIR = config.BASE_DIR


@bp.route('/')
def serve_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@bp.route('/<path:path>')
def serve_static(path):
    """Serve only browser assets, never source/config/runtime files."""
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or '..' in normalized.parts:
        abort(404)
    root_assets = {
        'index.html', 'styles.css', 'script.js', 'auth.js', 'characters.js',
        'logo.jpg', 'favicon.ico', 'index.json',
    }
    allowed_prefixes = ('avatars/', 'characters/', 'assets/', 'css/', 'js/', 'chat/')
    if path not in root_assets and not path.startswith(allowed_prefixes):
        abort(404)
    return send_from_directory(STATIC_DIR, path)

@bp.route('/chat/<path:filename>')
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

@bp.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(STATIC_DIR, 'css'), filename)

@bp.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(STATIC_DIR, 'js'), filename)

@bp.route('/favicon.ico')
def favicon():
    return send_from_directory(STATIC_DIR, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@bp.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')
