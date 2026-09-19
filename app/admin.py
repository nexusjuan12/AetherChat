"""Administration for invite-only accounts and deployment feature flags."""
from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import config
from .extensions import db
from .models import Character, FeatureFlag, User, VoiceProfile

bp = Blueprint('admin', __name__)


def _admin_only():
    if not current_user.is_admin:
        abort(403)


@bp.route('/admin-dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('static_routes.serve_index'))
    return render_template('admin-dashboard.html')


@bp.route('/api/admin/users/<user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    _admin_only()
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.is_active = bool((request.get_json(silent=True) or {}).get('status', not user.is_active))
    db.session.commit()
    return jsonify({'message': 'User status updated'})


@bp.route('/api/admin/users')
@login_required
def get_users():
    _admin_only()
    return jsonify([{
        'id': user.id, 'username': user.username, 'email': user.email,
        'auth_provider': user.auth_provider, 'is_active': user.is_active,
        'is_admin': user.is_admin,
    } for user in User.query.order_by(User.username).all()])


@bp.route('/api/admin/features', methods=['GET', 'PUT'])
@login_required
def feature_flags():
    _admin_only()
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        for key in ('video', 'story'):
            if key not in data:
                continue
            flag = db.session.get(FeatureFlag, key) or FeatureFlag(key=key)
            flag.enabled = bool(data[key])
            flag.updated_by = current_user.id
            db.session.add(flag)
        db.session.commit()
    flags = {flag.key: flag.enabled for flag in FeatureFlag.query.all()}
    return jsonify({
        'video': flags.get('video', config.VIDEO_ENABLED_DEFAULT),
        'story': flags.get('story', config.STORY_ENABLED_DEFAULT),
    })


@bp.route('/api/admin/stats')
@login_required
def get_admin_stats():
    _admin_only()
    return jsonify({
        'total_users': User.query.count(),
        'total_characters': Character.query.count(),
        'pending_voice_profiles': VoiceProfile.query.filter_by(visibility='public', approval_status='pending').count(),
    })
