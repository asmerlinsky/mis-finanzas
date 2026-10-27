# mis-finanzas — backend (uv, FastAPI) + frontend (npm, Vite)

set shell := ["bash", "-c"]

backend := "backend"
frontend := "frontend"

# List recipes
default:
    @just --list

# Install backend and frontend dependencies
setup:
    cd {{backend}} && uv sync
    cd {{frontend}} && npm ci

# API on :8000 (auto-reload) and Vite on :5173, which proxies /api to it
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (cd {{backend}} && uv run uvicorn mis_finanzas.main:create_app --factory --reload \
        --host 127.0.0.1 --port 8000) &
    (cd {{frontend}} && npm run dev) &
    wait

# Build the frontend and serve everything from the API process on :8000
serve: build
    cd {{backend}} && MIS_FINANZAS_FRONTEND_DIST="$(realpath ../{{frontend}}/dist)" uv run mis-finanzas

# Production build of the frontend
build:
    cd {{frontend}} && npm run build

# Run all tests
test:
    cd {{backend}} && uv run pytest
    cd {{frontend}} && npm test

# Run one test file: just test-file backend/tests/test_api.py (or a frontend/src/... file)
test-file path:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{path}}" in
        backend/*) cd {{backend}} && uv run pytest "${PWD%/backend}/{{path}}" ;;
        frontend/*) cd {{frontend}} && npx vitest run "${PWD%/frontend}/{{path}}" ;;
        *) echo "path must start with backend/ or frontend/" >&2; exit 1 ;;
    esac

# Redacted sample in samples/ from an .xlsx or .pdf: just redact ~/Downloads/mov.pdf --name "Full Name"
[positional-arguments]
redact file *args:
    uv run --project {{backend}} python -m mis_finanzas.tools.redact "$@"

# Draw a JSON sample back as a PDF to review it: just preview samples/x.redacted.json
preview sample:
    uv run --project {{backend}} python -m mis_finanzas.tools.render_sample "{{sample}}"

# Lint only
lint:
    cd {{backend}} && uv run ruff check src tests
    cd {{frontend}} && npm run lint

# All quality checks: lint, formatting, types
check:
    cd {{backend}} && uv run ruff check src tests
    cd {{backend}} && uv run ruff format --check src tests
    cd {{backend}} && uv run mypy src tests
    cd {{frontend}} && npm run lint
    cd {{frontend}} && npm run typecheck

# Auto-format and auto-fix
format:
    cd {{backend}} && uv run ruff format src tests
    cd {{backend}} && uv run ruff check --fix src tests
