"""
Authentication: username/password registration and login (no OAuth, no
email verification - this repo is the basic-auth home-deployment sibling of
AetherChatV3), plus the login_manager callbacks. Moved out of the original
monolithic webserver.py.
"""
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, redirect, url_for, render_template, session
from flask_login import login_user, logout_user, login_required, current_user

from .extensions import db, login_manager
from .models import User

bp = Blueprint('auth', __name__)


@login_manager.unauthorized_handler
def unauthorized():
    if request.blueprint == 'api' or request.path.startswith('/api/') or request.path.startswith('/auth/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('static_routes.serve_index'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

@bp.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
        
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already taken'}), 409
        
    user = User(
        username=data['username'],
        email=f"{data['username']}@temp.com",  # Temporary email since model requires it
        created_at=datetime.utcnow()
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        session.permanent = True
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'credits': user.credits,
                'is_admin': user.is_admin
            }
        }), 201
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing credentials'}), 400
        
    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        login_user(user, remember=True)
        session.permanent = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'credits': user.credits,
                'is_admin': user.is_admin
            }
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@bp.route('/auth/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out successfully'}), 200

@bp.route('/auth/user')
@login_required
def get_user():
    return jsonify({
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'username': current_user.username,
            'credits': current_user.credits,  # Added missing comma here
            'is_admin': current_user.is_admin
        }
    }), 200

@bp.route('/login')
def login_page():
    return render_template('login.html', google_client_id=os.getenv('GOOGLE_CLIENT_ID'))

@bp.route('/register')
def register_page():
    return render_template('register.html', google_client_id=os.getenv('GOOGLE_CLIENT_ID'))
