#!/usr/bin/env sh
set -eu

: "${SECRET_KEY:?Set SECRET_KEY in the environment or .env before starting AetherChat.}"
exec gunicorn --workers 2 --threads 4 --bind "${HOST:-127.0.0.1}:${PORT:-8081}" webserver:app
