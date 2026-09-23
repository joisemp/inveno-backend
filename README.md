# Inveno API

Production-ready, async-first Django REST Framework API.

**Stack:** Django 5 · DRF · PostgreSQL 16 · Redis 7 · Celery · JWT Auth · DigitalOcean Spaces · Railway · GHCR

---

## Quick Start (Development)

### 1. Clone & configure

```bash
git clone https://github.com/YOUR_ORG/inveno-api.git
cd inveno-api
cp .env.example .env
# Edit .env — the defaults work out-of-the-box for local Docker dev
```

### 2. Start the stack

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/docs/ |
| Frontend guide | http://localhost:8000/api/docs/frontend/ |
| ReDoc | http://localhost:8000/api/redoc/ |
| Django Admin | http://localhost:8000/admin/ |

### 3. Demo logins (seeded after migrate)

First boot creates a demo org, catalog, vendors, and purchase-flow rows.
Use attached `docker compose up` (not `-d`); later starts pause so you can type **k** keep / **w** wipe. Password for all: `DemoPass123!`.

| Login (email) | Role |
|---|---|
| `super@inveno.local` | super_admin |
| `admin@demo.inveno.local` | central_admin |
| `ops@demo.inveno.local` | operation_incharge |
| `warehouse@demo.inveno.local` | warehouse_manager |
| `space@demo.inveno.local` | space_incharge |

```bash
# Wipe and recreate
docker compose exec -it api python manage.py seed_demo --reset
```

Set `SEED_DEMO=false` to skip. Production never seeds.

### 4. Run tests

```bash
docker compose exec api pytest
```

---

## Project Structure

```
inveno-api/
├── config/                  # Django project package
│   ├── settings/
│   │   ├── base.py          # Shared settings
│   │   ├── development.py   # Dev (console email, colorlog, debug toolbar)
│   │   └── production.py    # Prod (DO Spaces, JSON logging, HTTPS)
│   ├── asgi.py              # ASGI entrypoint (uvicorn)
│   ├── celery.py            # Celery app
│   └── urls.py              # Root URL config
├── apps/
│   ├── users/               # Custom User model + auth endpoints
│   └── healthcheck/         # /api/health/ endpoint
├── tests/                   # pytest test suite
├── docker/api/              # Dockerfiles + entrypoint
├── requirements/            # base / development / production
├── docker-compose.yml           # Dev stack
├── docker-compose.frontend-dev.yml  # For frontend devs
├── docker-compose.react.yml         # Full-stack with React
├── railway.json             # Railway deployment config
└── .github/workflows/release.yml   # CI/CD pipeline
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list with descriptions.

### Required for all environments

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key (generate with `python -c "import secrets; print(secrets.token_hex(50))"`) |
| `PROCESS_SIGNING_KEY` | HMAC key for the purchase-flow process trail (not `DJANGO_SECRET_KEY`; generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `REDIS_URL` | Redis connection URL |

Optional: `JWT_SIGNING_KEY` — HMAC key for JWTs. If unset, `DJANGO_SECRET_KEY` is used. Rotating it invalidates outstanding tokens without rotating Django's secret.

### Local Docker only

| Variable | Description |
|---|---|
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_HOST` | Database host (`db` in Compose) |
| `POSTGRES_PORT` | Database port (`5432`) |

### Production only (Railway)

Railway automatically injects `DATABASE_URL` and `REDIS_URL` when you add Postgres/Redis plugins. Production settings parse `DATABASE_URL` — do not set `POSTGRES_*` on Railway.

| Variable | Description |
|---|---|
| `DJANGO_SETTINGS_MODULE` | Set to `config.settings.production` |
| `DJANGO_SECRET_KEY` | Strong secret key |
| `DJANGO_ALLOWED_HOSTS` | Your Railway domain + custom domain |
| `DATABASE_URL` | Injected by Railway Postgres (`postgresql://...`) |
| `CORS_ALLOWED_ORIGINS` | Your frontend URL(s) |
| `DO_SPACES_KEY` | DigitalOcean Spaces access key |
| `DO_SPACES_SECRET` | DigitalOcean Spaces secret key |
| `DO_SPACES_BUCKET` | Spaces bucket name |
| `DO_SPACES_REGION` | Spaces region (e.g. `nyc3`) |
| `EMAIL_HOST` | SMTP host |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password |

---

## Celery (Background Tasks)

Workers and beat scheduler are included in `docker-compose.yml`.

On Railway, deploy the same image as **separate services** with these start commands:

- **Worker:** `celery -A config worker --loglevel=info --concurrency=2`
- **Beat:** `celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler`

Both services share the same `DATABASE_URL` and `REDIS_URL` from Railway plugins.

---

## DigitalOcean Spaces (Static & Media — Production)

Static files and media uploads are served from DigitalOcean Spaces in production.

1. Create a Spaces bucket in your DO account
2. Set the required env vars (`DO_SPACES_*`) in Railway
3. Static files are uploaded automatically on deploy via `collectstatic`
4. Media files are uploaded on user upload

**Bucket CORS** — add this rule in your Spaces bucket settings to allow browser uploads:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["https://yourdomain.com"],
    "MaxAgeSeconds": 3600
  }
]
```

---

## Deployment (Railway)

### One-time setup

1. Create a Railway project and add **Postgres** and **Redis** plugins
2. Add a service → **Deploy from image** → `ghcr.io/YOUR_ORG/inveno-api:latest`
3. Set all required production env vars in the service settings
4. Copy the **Deploy Webhook URL** from Railway → Settings → Deploy
5. Add it as `RAILWAY_WEBHOOK_URL` in your GitHub repo secrets

### Releasing a new version

```bash
# Tag and push your release on GitHub
# GitHub → Releases → Draft a new release → Tag: v1.2.0 → Publish

# GitHub Actions will automatically:
# 1. Build the prod image
# 2. Push ghcr.io/YOUR_ORG/inveno-api:v1.2.0 + :latest to GHCR
# 3. Trigger Railway to redeploy with the new image
```

### Rollback

In Railway dashboard → Deployments → click any previous deployment → **Redeploy**.

Or update the image tag to a specific version: `ghcr.io/YOUR_ORG/inveno-api:v1.1.0`

---

## Auth

Login uses **email + password** — there is no `username` field.

See [FRONTEND_API.md](FRONTEND_API.md) for the complete API reference for frontend developers.

---

## Running Tests

```bash
# Inside Docker
docker compose exec api pytest

# Locally (with venv)
pip install -r requirements/development.txt
pytest
```

---

## Adding a New App

```bash
docker compose exec api python manage.py startapp myapp apps/myapp
```

Then add `"apps.myapp"` to `LOCAL_APPS` in `config/settings/base.py`.
