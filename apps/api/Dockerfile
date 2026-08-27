# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base
RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin app
WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps apps
RUN uv sync --frozen --no-dev --package merchantos-api

FROM base AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENV=production ALEMBIC_INI=/app/packages/db/alembic.ini
COPY --from=builder /app /app
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "merchantos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
