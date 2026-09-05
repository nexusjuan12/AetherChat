"""
Shared Flask extension instances.

Created unbound here (no app passed to the constructor) and attached to the
real app object inside create_app() via .init_app(app). Every blueprint
module imports db/login_manager from here rather than from the app package
itself, so there's no import cycle between this module and app/__init__.py.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
