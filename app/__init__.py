"""
Application factory. Assembles the Flask app from the extensions, models,
and blueprints that used to all live inline in one 2600-line webserver.py.

Route paths, JSON contracts, config values, and startup side effects
(directory creation, db.create_all()) are unchanged from the original -
this only changes which file each piece of code lives in.
"""
import os
from datetime import timedelta

from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

import config
from .extensions import db, login_manager
from .migrations import run_migrations
from .security import register_security_headers


def create_app():
    # Load environment variables before anything below reads them (Stripe/
    # KOBOLD_API/SECRET_KEY etc. are all read from os.environ at import time
    # by the blueprint modules).
    load_dotenv(config.ENV_FILE)

    app = Flask(
        __name__.split('.')[0],
        template_folder=config.TEMPLATES_DIR,
        static_folder=config.BASE_DIR,
    )

    CORS(
        app,
        supports_credentials=True,
        resources={
            r"/*": {
                # Was origins="*" combined with supports_credentials=True -
                # browsers reject that combination for credentialed
                # requests, and if they didn't, it would let any site ride
                # a logged-in user's session cookie. Set CORS_ORIGINS
                # (comma-separated) for your home-network deployment.
                "origins": config.CORS_ORIGINS,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "X-CSRF-Token"],
                "supports_credentials": True,
            }
        },
    )

    if not os.getenv('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY is not set. Refusing to start with a default/well-known '
            'key, since that would let anyone forge session cookies. Set '
            'SECRET_KEY in your .env or environment.'
        )

    app.config.update(
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{config.DB_PATH}',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv('SECRET_KEY'),
        STATIC_FOLDER=config.BASE_DIR,
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=31),
        SESSION_COOKIE_DOMAIN=config.SESSION_COOKIE_DOMAIN,
        SESSION_COOKIE_PATH='/',
        MAX_CONTENT_LENGTH=1024 * 1024 * 1024,  # 1GB max-size
    )

    # Directory configuration - ensure everything the blueprints will read
    # from/write to exists before the first request.
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.CHARACTER_FOLDER, exist_ok=True)
    os.makedirs(config.VOICE_SAMPLE_DIR, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    # Story Mode is known incomplete and deliberately not registered unless a
    # future repair pass makes it safe to enable.
    from . import auth, characters, admin, media, static_routes

    app.register_blueprint(auth.bp)
    app.register_blueprint(characters.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(media.bp)
    app.register_blueprint(static_routes.bp)

    register_security_headers(app)

    with app.app_context():
        db.create_all()
        run_migrations()

    # Register worker handlers here rather than only in webserver.py. This
    # keeps chat and speech jobs functional when deployed under Gunicorn.
    from .media import kobold_handler, tts_handler
    from queue_system import setup_queue_handlers
    setup_queue_handlers(kobold_handler, tts_handler)

    return app
