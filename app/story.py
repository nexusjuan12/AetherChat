"""Reserved Story Mode boundary.

The original collaborative-story implementation depended on the retired RVC
and credits code paths and was not reliable. It is intentionally not
registered by the application factory until it is rebuilt against the current
provider and ownership contracts.
"""
from flask import Blueprint, jsonify
from flask_login import login_required

bp = Blueprint('story', __name__)


@bp.route('/story/<path:_path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def disabled(_path):
    return jsonify({'error': 'Story Mode is disabled pending repair.'}), 410
