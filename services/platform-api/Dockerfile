FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data \
    && chown app:app /data

COPY pyproject.toml ./
RUN python -c "import subprocess, sys, tomllib; config=tomllib.load(open('pyproject.toml', 'rb')); subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *config['project']['dependencies']])"
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY manage.py ./
COPY mold_platform ./mold_platform
COPY platform_core ./platform_core
COPY scripts ./scripts

RUN pip install --no-cache-dir --no-deps . && chmod +x scripts/*.sh

FROM base AS development
RUN python -c "import subprocess, sys, tomllib; config=tomllib.load(open('pyproject.toml', 'rb')); subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *config['project']['optional-dependencies']['dev']])"
USER app

FROM base AS production
USER app
CMD ["gunicorn", "mold_platform.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
