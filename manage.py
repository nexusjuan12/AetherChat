"""Small administration CLI for reproducible self-hosted deployments."""
from __future__ import annotations

import argparse
import getpass
import secrets

from app import create_app
from app.extensions import db
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)
    bootstrap = subparsers.add_parser('bootstrap-admin')
    bootstrap.add_argument('--username', required=True)
    bootstrap.add_argument('--email', required=True)
    subparsers.add_parser('new-secret')
    args = parser.parse_args()

    if args.command == 'new-secret':
        print(secrets.token_urlsafe(48))
        return

    password = getpass.getpass('Password (12+ characters): ')
    if len(password) < 12:
        raise SystemExit('Password must be at least 12 characters.')
    app = create_app()
    with app.app_context():
        if User.query.filter((User.username == args.username) | (User.email == args.email)).first():
            raise SystemExit('Username or email already exists.')
        user = User(username=args.username, email=args.email, auth_provider='local', is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    print(f'Created local administrator {args.username}.')


if __name__ == '__main__':
    main()
