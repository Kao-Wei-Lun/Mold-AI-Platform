FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data \
    && chown app:app /data

COPY pyproject.toml ./
COPY manage.py ./
COPY mold_platform ./mold_platform
COPY platform_core ./platform_core
COPY scripts ./scripts

RUN pip install --no-cache-dir . && chmod +x scripts/*.sh
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS development
RUN pip install --no-cache-dir ".[dev]"
USER app

FROM base AS production
USER app
CMD ["gunicorn", "mold_platform.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
