"""
Admin dashboard and user-management endpoints. Not in the original plan's
module list verbatim, but split out from character moderation since they're
a distinct concern (user accounts/credits vs. character approval).
"""
import os
import json

from flask import Blueprint, request, jsonify, redirect, url_for, render_template, make_response
from flask_login import login_required, current_user

import config
from .extensions import db
from .models import User, CreditTransaction

bp = Blueprint('admin', __name__)

CHARACTER_FOLDER = config.CHARACTER_FOLDER


@bp.route('/admin-dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('static_routes.serve_index'))
    try:
        response = make_response(render_template('admin-dashboard.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error rendering admin dashboard: {str(e)}")
        return redirect(url_for('static_routes.serve_index'))

@bp.route('/api/admin/users/<user_id>/toggle-status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        user = User.query.get_or_404(user_id)
        data = request.json
        user.is_active = data.get('status', not user.is_active)
        db.session.commit()
        return jsonify({'message': 'User status updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/admin/users/<user_id>/credits', methods=['POST'])
@login_required
def modify_user_credits(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        user = User.query.get_or_404(user_id)
        data = request.json
        amount = data.get('amount', 0)
        
        # Create a transaction record
        transaction = CreditTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type='admin_modification',
            description=f'Admin credit modification'
        )
        
        user.credits = amount  # Set to new amount
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({'message': 'Credits updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/admin/users')
@login_required
def get_users():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        users = User.query.all()
        return jsonify([{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'credits': user.credits,
            'is_active': user.is_active
        } for user in users])
    except Exception as e:
        print(f"Error in get_users: {str(e)}")  # Add logging
        return jsonify({'error': str(e)}), 500

@bp.route('/api/admin/stats')
@login_required
def get_admin_stats():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        # Initialize counters
        stats = {
            'total_characters': 0,
            'pending_characters': 0,
            'approved_characters': 0,
            'rejected_characters': 0,
            'private_characters': 0,
            'public_characters': 0,
            'total_users': 0,
            'total_transactions': 0
        }
        
        # Make sure CHARACTER_FOLDER exists
        if os.path.exists(CHARACTER_FOLDER):
            for filename in os.listdir(CHARACTER_FOLDER):
                if filename.endswith('.json'):
                    try:
                        stats['total_characters'] += 1
                        with open(os.path.join(CHARACTER_FOLDER, filename), 'r', encoding='utf-8') as f:
                            char_data = json.load(f)
                            if char_data.get('isPrivate', False):
                                stats['private_characters'] += 1
                            elif char_data.get('isApproved', False):
                                stats['approved_characters'] += 1
                                stats['public_characters'] += 1
                            elif char_data.get('approvalStatus') == 'pending':
                                stats['pending_characters'] += 1
                            elif char_data.get('approvalStatus') == 'rejected':
                                stats['rejected_characters'] += 1
                    except Exception as e:
                        print(f"Error reading character file {filename}: {str(e)}")
                        continue
        
        # Get user and transaction counts from database
        try:
            stats['total_users'] = User.query.count()
            stats['total_transactions'] = CreditTransaction.query.count()
        except Exception as e:
            print(f"Error getting database counts: {str(e)}")
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error in get_admin_stats: {str(e)}")
        return jsonify({
            'total_characters': 0,
            'pending_characters': 0,
            'approved_characters': 0,
            'rejected_characters': 0,
            'private_characters': 0,
            'public_characters': 0,
            'total_users': 0,
            'total_transactions': 0
        })
