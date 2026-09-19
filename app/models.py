"""Persistent application models. Runtime media and provider secrets stay outside Git."""
import uuid
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def uuid_string():
    return str(uuid.uuid4())


class User(UserMixin, db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    auth_provider = db.Column(db.String(32), nullable=False, default='local')
    external_subject = db.Column(db.String(255), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    characters = db.relationship('Character', backref='creator', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)


class Invite(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    token_hash = db.Column(db.String(128), unique=True, nullable=False)
    created_by = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    redeemed_at = db.Column(db.DateTime)
    redeemed_by = db.Column(db.String(36), db.ForeignKey('user.id'))
    revoked_at = db.Column(db.DateTime)

    @property
    def is_available(self):
        return not self.redeemed_at and not self.revoked_at and self.expires_at > datetime.utcnow()


class FeatureFlag(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(36), db.ForeignKey('user.id'))


class VoiceProfile(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    owner_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    provider_profile_id = db.Column(db.String(255))
    sample_path = db.Column(db.String(255), nullable=False)
    reference_text = db.Column(db.Text, nullable=False)
    visibility = db.Column(db.String(16), nullable=False, default='private')
    approval_status = db.Column(db.String(16), nullable=False, default='approved')
    consent_confirmed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.String(36), db.ForeignKey('user.id'))
    disabled_at = db.Column(db.DateTime)

    def is_usable_by(self, user):
        if self.disabled_at:
            return False
        if self.owner_id == user.id or user.is_admin:
            return True
        return self.visibility == 'public' and self.approval_status == 'approved'

    def to_dict(self):
        return {
            'id': self.id,
            'display_name': self.display_name,
            'visibility': self.visibility,
            'approval_status': self.approval_status,
            'created_at': self.created_at.isoformat(),
        }


class Character(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    avatar_path = db.Column(db.String(255), nullable=False)
    background_path = db.Column(db.String(255))
    tts_voice = db.Column(db.String(50), nullable=False, default='default')
    voice_profile_id = db.Column(db.String(36), db.ForeignKey('voice_profile.id'))
    category = db.Column(db.String(50))
    is_private = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    settings = db.Column(db.JSON)
    greetings = db.Column(db.JSON)
    voice_profile = db.relationship('VoiceProfile', foreign_keys=[voice_profile_id])

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'description': self.description,
            'avatar': self.avatar_path, 'background': self.background_path,
            'category': self.category, 'is_private': self.is_private,
            'is_approved': self.is_approved,
            'voice_profile_id': self.voice_profile_id,
            'created_at': self.created_at.isoformat(), 'settings': self.settings,
        }


class CharacterApprovalQueue(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    reviewer_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    review_notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    character = db.relationship('Character')
    reviewer = db.relationship('User')


class StorySession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    scenario = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    max_characters = db.Column(db.Integer, default=4)
    settings = db.Column(db.JSON)


class StoryCharacter(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=uuid_string)
    session_id = db.Column(db.String(36), db.ForeignKey('story_session.id'), nullable=False)
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'))
    position = db.Column(db.Integer)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_placeholder = db.Column(db.Boolean, default=False)
    placeholder_name = db.Column(db.String(100), default='Empty Panel')
