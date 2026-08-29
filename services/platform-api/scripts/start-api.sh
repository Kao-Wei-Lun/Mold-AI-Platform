#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py seed_master_data
exec python manage.py runserver 0.0.0.0:8000
