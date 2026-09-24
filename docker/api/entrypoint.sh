#!/bin/sh
set -e

echo "==> Waiting for database..."
until python -c "
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', '${DJANGO_SETTINGS_MODULE:-config.settings.development}')
django.setup()
from django.db import connection
connection.ensure_connection()
print('Database is ready.')
" 2>/dev/null; do
  echo "Database not ready — retrying in 2s..."
  sleep 2
done

echo "==> Migration plan ($(date -u +%Y-%m-%dT%H:%M:%SZ))..."
python manage.py showmigrations

echo "==> Running migrations..."
if ! python manage.py migrate --noinput; then
  echo ""
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "  MIGRATION FAILED — deployment aborted   "
  echo "  Check the output above for details.     "
  echo "  Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo ""
  exit 1
fi

# Demo seed is development-only (command no-ops when DEBUG is false).
# Celery shares this image/entrypoint — do not prompt, seed, or collectstatic
# on workers (collectstatic --clear would wipe the shared Spaces prefix).
if [ "$1" != "celery" ]; then
  echo "==> Demo seed..."
  python manage.py seed_demo

  echo "==> Collecting static files..."
  python manage.py collectstatic --noinput --clear
fi

echo "==> Starting server..."
exec "$@"
