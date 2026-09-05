"""
Database models. Moved verbatim out of the original monolithic webserver.py
- no field or method changed, only the module they live in.

StripeTransaction, SubscriptionTier, STRIPE_PRICE_IDS, and CREDIT_PACKAGES
are dead leftovers from this repo being forked off AetherChatV3 - this
(home-deployment, no-payment) repo has no Stripe routes anywhere and never
references any of these. Kept for behavior parity with the original file
rather than pruned, since that's a separate decision from the module split.
"""
import os
import uuid
import time
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    credits = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False) 
    characters = db.relationship('Character', backref='creator', lazy=True)
    stripe_customer_id = db.Column(db.String(100), unique=True)
    subscription_tier = db.Column(db.String(20), default='explorer')
    subscription_status = db.Column(db.String(20), default='free')
    subscription_id = db.Column(db.String(100), unique=True)
    monthly_credits = db.Column(db.Integer, default=1000)
    last_credit_refresh = db.Column(db.DateTime, default=datetime.utcnow)

    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_credits(self):
        return self.credits
    
    def add_credits(self, amount):
        self.credits += amount
        db.session.commit()
        
    def deduct_credits(self, amount):
        if self.credits >= amount:
            self.credits -= amount
            db.session.commit()
            return True
        return False

    # Add the new method here, indented at the same level as the others
    def deduct_credits_atomic(self, amount):
        """
        Atomically deduct credits from user balance.
        Returns True if successful, False if insufficient credits.
        """
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                # Create a new session for this transaction
                with db.session.begin():
                    user = db.session.query(User).filter(
                        User.id == self.id
                    ).with_for_update().first()

                    if not user or user.credits < amount:
                        return False

                    # Update credits directly in the transaction
                    user.credits = user.credits - amount
                    return True

            except Exception as e:
                db.session.rollback()
                if attempt == max_retries - 1:
                    print(f"Error in atomic credit deduction: {e}")
                    return False
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff

        return False  # All retries failed
        return False  # All retries failed

class StorySession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    scenario = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    max_characters = db.Column(db.Integer, default=4)
    settings = db.Column(db.JSON)

class StoryCharacter(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey('story_session.id'), nullable=False)
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'), nullable=True)  # Nullable for placeholders
    position = db.Column(db.Integer)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_placeholder = db.Column(db.Boolean, default=False)
    placeholder_name = db.Column(db.String(100), default="Empty Panel")

class StripeTransaction(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # Amount in cents
    credits = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'credit_purchase' or 'subscription'
    status = db.Column(db.String(20), nullable=False)
    stripe_payment_id = db.Column(db.String(100), unique=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Changed backref name to avoid conflict
    user = db.relationship('User', backref=db.backref('stripe_payment_transactions', lazy=True))

class SubscriptionTier(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(50), nullable=False)  # 'explorer', 'creator', 'master'
    price = db.Column(db.Integer, nullable=False)    # Price in cents
    monthly_credits = db.Column(db.Integer)          # None for unlimited
    features = db.Column(db.JSON)

class CreditTransaction(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

class Character(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    creator_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    avatar_path = db.Column(db.String(255), nullable=False)
    background_path = db.Column(db.String(255))
    tts_voice = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50))
    is_private = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    settings = db.Column(db.JSON)
    greetings = db.Column(db.JSON) 

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar_path,
            'background': self.background_path,
            'category': self.category,
            'is_private': self.is_private,
            'is_approved': self.is_approved,
            'created_at': self.created_at.isoformat(),
            'settings': self.settings
        }

class CharacterApprovalQueue(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = db.Column(db.String(36), db.ForeignKey('character.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    reviewer_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    review_notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    
    character = db.relationship('Character')
    reviewer = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'character': self.character.to_dict(),
            'submitted_at': self.submitted_at.isoformat(),
            'status': self.status,
            'review_notes': self.review_notes,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }

STRIPE_PRICE_IDS = {
    'creator': os.getenv('STRIPE_CREATOR_PRICE_ID'),  # $9.99 monthly
    'master': os.getenv('STRIPE_MASTER_PRICE_ID'),    # $24.99 monthly
}

CREDIT_PACKAGES = {
    1000: 500,   # 1000 credits for $5.00
    2500: 1000   # 2500 credits for $10.00
}
