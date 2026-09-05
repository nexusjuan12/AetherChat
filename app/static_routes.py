"""
Static file serving (SPA index, css/js/chat assets, favicon) and the two
static legal pages. Moved out of the original monolithic webserver.py.
"""
import os

from flask import Blueprint, send_from_directory, render_template

import config

bp = Blueprint('static_routes', __name__)

STATIC_DIR = config.BASE_DIR


@bp.route('/')
def serve_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@bp.route('/<path:path>')
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
