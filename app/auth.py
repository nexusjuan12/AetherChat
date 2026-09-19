"""Invite-only local auth and trusted Authentik identity mapping."""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

import config
from .extensions import db, login_manager
from .models import Invite, User

bp = Blueprint('auth', __name__)
_attempts: dict[str, list[datetime]] = {}
_attempt_lock = threading.Lock()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _client_key() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()


def _allow_login_attempt() -> bool:
    now = datetime.utcnow()
    with _attempt_lock:
        recent = [item for item in _attempts.get(_client_key(), []) if item > now - timedelta(minutes=15)]
        recent.append(now)
        _attempts[_client_key()] = recent
        return len(recent) <= 10


def _authentik_groups() -> set[str]:
    raw = request.headers.get('X-Authentik-Groups', '')
    return {group.strip().lower() for group in raw.split(',') if group.strip()}


def _authentik_user() -> User | None:
    if config.AUTH_MODE != 'authentik' or not config.TRUST_AUTHENTIK_HEADERS:
        return None
    subject = request.headers.get('X-Authentik-Uid', '').strip()
    username = request.headers.get('X-Authentik-Username', '').strip()
    groups = _authentik_groups()
    if not subject or not username or not (config.AUTHENTIK_REQUIRED_GROUPS & groups):
        return None
    user = User.query.filter_by(external_subject=subject).first()
    if user:
        if user.username != username and not User.query.filter(User.username == username, User.id != user.id).first():
            user.username = username
        user.is_admin = 'admins' in groups
        user.last_login = datetime.utcnow()
        db.session.commit()
        return user
    email = request.headers.get('X-Authentik-Email', '').strip() or f'{subject}@authentik.invalid'
    if User.query.filter_by(email=email).first():
        email = f'{subject}@authentik.invalid'
    if User.query.filter_by(username=username).first():
        safe_subject = re.sub(r'[^a-zA-Z0-9_-]', '', subject)[-8:] or 'member'
        username = f'{username}-{safe_subject}'[:80]
    user = User(username=username, email=email, auth_provider='authentik', external_subject=subject)
    user.is_admin = 'admins' in groups
    db.session.add(user)
    db.session.commit()
    return user


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


@login_manager.request_loader
def load_request_user(_request):
    return _authentik_user()


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/') or request.path.startswith('/v1/') or request.path.startswith('/auth/'):
        return jsonify({'error': 'Authentication required'}), 401
    if config.AUTH_MODE == 'authentik':
        return jsonify({'error': 'Authentik membership required'}), 403
    return redirect(url_for('auth.login_page'))


@bp.before_app_request
def enforce_auth_mode():
    if config.AUTH_MODE not in {'local_invite', 'authentik'}:
        raise RuntimeError('AUTH_MODE must be local_invite or authentik')
    if config.AUTH_MODE == 'authentik' and request.endpoint not in {'static_routes.favicon'}:
        if not _authentik_user():
            abort(403)


def _local_mode_only():
    if config.AUTH_MODE != 'local_invite':
        abort(404)


@bp.route('/auth/login', methods=['POST'])
def login():
    _local_mode_only()
    if not _allow_login_attempt():
        return jsonify({'error': 'Too many login attempts. Try again later.'}), 429
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    user = User.query.filter_by(username=username, auth_provider='local').first()
    if not user or not user.is_active or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    login_user(user, remember=True)
    session.permanent = True
    session['csrf_token'] = secrets.token_urlsafe(32)
    user.last_login = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Login successful', 'user': serialize_user(user), 'csrf_token': session['csrf_token']})


@bp.route('/auth/register', methods=['POST'])
def register():
    _local_mode_only()
    data = request.get_json(silent=True) or {}
    token = str(data.get('invite', '')).strip()
    username = str(data.get('username', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    if not token or not username or not email or len(password) < 12:
        return jsonify({'error': 'Invite, username, email, and a 12-character password are required'}), 400
    invite = Invite.query.filter_by(token_hash=_token_hash(token)).first()
    if not invite or not invite.is_available:
        return jsonify({'error': 'Invite is invalid or expired'}), 403
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'Username or email is already registered'}), 409
    user = User(username=username, email=email, auth_provider='local')
    user.set_password(password)
    invite.redeemed_at = datetime.utcnow()
    invite.redeemed_by = user.id
    db.session.add(user)
    db.session.flush()
    invite.redeemed_by = user.id
    db.session.commit()
    login_user(user, remember=True)
    session.permanent = True
    session['csrf_token'] = secrets.token_urlsafe(32)
    return jsonify({'message': 'Account created', 'user': serialize_user(user), 'csrf_token': session['csrf_token']}), 201


@bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    if config.AUTH_MODE == 'local_invite':
        logout_user()
        session.clear()
    return jsonify({'message': 'Logged out'})


@bp.route('/auth/user')
@login_required
def get_user():
    return jsonify({'user': serialize_user(current_user), 'auth_mode': config.AUTH_MODE})


@bp.route('/auth/csrf')
@login_required
def csrf_token():
    token = session.setdefault('csrf_token', secrets.token_urlsafe(32))
    return jsonify({'csrf_token': token})


@bp.route('/login')
def login_page():
    if config.AUTH_MODE == 'authentik':
        abort(404)
    return render_template('login.html')


@bp.route('/register')
def register_page():
    if config.AUTH_MODE == 'authentik':
        abort(404)
    return render_template('register.html')


@bp.route('/api/admin/invites', methods=['POST'])
@login_required
def create_invite():
    if not current_user.is_admin:
        abort(403)
    data = request.get_json(silent=True) or {}
    hours = max(1, min(int(data.get('expires_in_hours', 168)), 24 * 30))
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token_hash=_token_hash(token), created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=hours),
    )
    db.session.add(invite)
    db.session.commit()
    return jsonify({'invite': token, 'expires_at': invite.expires_at.isoformat()}), 201


def serialize_user(user: User) -> dict:
    return {'id': user.id, 'username': user.username, 'email': user.email, 'is_admin': user.is_admin}
