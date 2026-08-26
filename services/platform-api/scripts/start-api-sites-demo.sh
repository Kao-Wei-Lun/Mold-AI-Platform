#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py deployment_preflight --profile quick-tunnel --strict
exec gunicorn mold_platform.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-300}" \
    --access-logfile - \
    --error-logfile -
