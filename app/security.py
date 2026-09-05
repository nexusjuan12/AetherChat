"""
Security/CORS response headers, applied to every response. Moved out of the
original monolithic webserver.py's @app.after_request hook.
"""
from flask import request

import config


def register_security_headers(app):
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
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')

        # Basic security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    app.after_request(after_request)
