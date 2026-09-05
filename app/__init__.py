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
                "allow_headers": ["Content-Type", "Authorization"],
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
        SESSION_COOKIE_SECURE=False,  # local/home deployment, not behind TLS by default
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

    db.init_app(app)
    login_manager.init_app(app)

    # Import blueprint modules only after db/login_manager are bound to the
    # app and env vars are loaded - several of them read os.environ at
    # import time. auth.py registers both @login_manager.user_loader and
    # @login_manager.unauthorized_handler as a side effect of being
    # imported. story.py imports from media.py, so media must be importable
    # first (Python resolves that on demand, order here doesn't matter).
    from . import auth, characters, admin, media, story, static_routes

    app.register_blueprint(auth.bp)
    app.register_blueprint(characters.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(media.bp)
    app.register_blueprint(story.bp)
    app.register_blueprint(static_routes.bp)

    # Also re-set model_cache's paths here, matching the original module's
    # top-level side effect (model_cache is a singleton shared with
    # tts_handler in app/media.py).
    from model_cache import model_cache
    model_cache._base_model_path = config.MODELS_DIR
    model_cache._input_dir = config.INPUT_DIR + os.sep
    model_cache._output_dir = config.OUTPUT_DIR + os.sep
    model_cache._cache_timeout = 1800  # 30 minutes timeout

    register_security_headers(app)

    with app.app_context():
        db.create_all()

    return app
