"""Small, dependency-free SQLite migration runner for self-hosted installs."""
from __future__ import annotations

from sqlalchemy import text

from .extensions import db


def _column_names(table: str) -> set[str]:
    rows = db.session.execute(text(f'PRAGMA table_info("{table}")')).mappings()
    return {row['name'] for row in rows}


def _add_column_if_missing(table: str, name: str, definition: str) -> None:
    if name not in _column_names(table):
        db.session.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))


def upgrade_001_identity_and_voice_profiles() -> None:
    """Keep legacy SQLite installations usable while adding the new entities."""
    _add_column_if_missing('user', 'auth_provider', "VARCHAR(32) NOT NULL DEFAULT 'local'")
    _add_column_if_missing('user', 'external_subject', 'VARCHAR(255)')
    _add_column_if_missing('character', 'voice_profile_id', 'VARCHAR(36)')
    db.session.commit()


def run_migrations() -> None:
    """Apply idempotent migrations after SQLAlchemy has created missing tables."""
    upgrade_001_identity_and_voice_profiles()
