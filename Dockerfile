FROM node:22-alpine AS web-build

WORKDIR /web

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data \
    && chown app:app /data

COPY services/platform-api/pyproject.toml ./
RUN python -c "import subprocess, sys, tomllib; config=tomllib.load(open('pyproject.toml', 'rb')); subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *config['project']['dependencies']])"
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY services/platform-api/manage.py ./
COPY services/platform-api/mold_platform ./mold_platform
COPY services/platform-api/platform_core ./platform_core
COPY services/platform-api/scripts ./scripts
COPY deploy/nginx-unified.conf /etc/nginx/nginx.conf
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /web/dist /usr/share/nginx/html

RUN pip install --no-cache-dir --no-deps . \
    && chmod +x scripts/*.sh \
    && chown -R app:app /usr/share/nginx/html

EXPOSE 8000 8001 8080

USER app

CMD ["gunicorn", "mold_platform.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
