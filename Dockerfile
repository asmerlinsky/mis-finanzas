# mis-finanzas: the frontend built with Node, served by the Python API.
# First run: set the login password (the server refuses to listen on 0.0.0.0 without one):
#   docker compose run --rm app mis-finanzas-password

FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY --from=frontend /src/dist ./frontend

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /backups \
    && chown app:app /data /backups
USER app

ENV PATH=/app/.venv/bin:$PATH \
    MIS_FINANZAS_DATA_DIR=/data \
    MIS_FINANZAS_HOST=0.0.0.0 \
    MIS_FINANZAS_PORT=8000 \
    MIS_FINANZAS_FRONTEND_DIST=/app/frontend
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["mis-finanzas"]
