"""
Security/CORS response headers, applied to every response. Moved out of the
original monolithic webserver.py's @app.after_request hook.
"""
import secrets

from flask import abort, request, session

import config


def register_security_headers(app):
    @app.before_request
    def csrf_protect():
        # Authentik requests are authenticated by Caddy headers rather than a
        # browser-owned Flask session. Local invite mode uses a per-session
        # token for state-changing authenticated API calls.
        if config.AUTH_MODE != 'local_invite' or request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return
        if request.path in {'/auth/login', '/auth/register'}:
            return
        # Login and registration authenticate themselves. Every other mutating
        # local-session request, including media uploads and character edits,
        # must present the session-bound token.
        expected = session.get('csrf_token')
        supplied = request.headers.get('X-CSRF-Token')
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, 'Missing or invalid CSRF token')

    def after_request(response):
        # Was: origin = request.headers.get('Origin', '*'); then always added
        # that origin to Access-Control-Allow-Origin alongside
        # Access-Control-Allow-Credentials: true. That combination means ANY
        # website can make authenticated (cookie-carrying) cross-origin requests
        # to this API and read the response - a full CORS bypass letting any
        # site ride a logged-in user's session. This ran independently of (and
        # undid the effect of) the flask_cors.CORS(...) config in
        # app/__init__.py, which is why it's fixed here too, not just there.
        # Only ever reflect an origin that's actually on the allowlist.
        origin = request.headers.get('Origin', '')
        if origin in config.CORS_ORIGINS:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-CSRF-Token')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')

        # Basic security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        return response

    app.after_request(after_request)
