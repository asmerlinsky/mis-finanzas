# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mis-finanzas` is a personal finance app for one owner in Argentina:
- a ledger of earnings and expenses;
- statement imports from the owner's bank, wallet and broker;
- every total shown in ARS and in USD at the daily MEP rate.

Later slices, not built yet: monotributo tracking from ARCA's "Mis Comprobantes" export, and
broker investments. The design and its decisions are in
`docs/specs/2026-10-27-mis-finanzas-design.md`. Read it before starting a new slice. The UI and
the domain terms are in Spanish.

**Hard constraint:** personal data is processed and stored only locally. No request may carry
personal data. Outbound HTTP goes through `market/http.py::PublicHttpClient` only: GET, HTTPS,
hosts in `Settings.public_hosts`. Always download whole public datasets, never one ticker or
account at a time, and at most once a day (enforced by `fetch_log`).

## Commands

```bash
just setup                      # uv sync + npm ci
just dev                        # API :8000 (reload) + Vite :5173 (proxies /api)
just serve                      # build frontend, serve everything from the API on :8000
just test                       # pytest + vitest
just test-file backend/tests/test_api.py      # one file (backend/... or frontend/...)
cd backend && uv run pytest tests/test_api.py::test_import_dedupes_same_file_and_overlaps
just check                      # ruff, ruff format --check, mypy --strict, oxlint, tsc
just format
```

Node comes from `n` (`/usr/local/bin/node`, v22). The apt `/usr/bin/node` v12 is too old.
`rm -rf` and `git commit` are denied in `.claude/settings.json`. The owner commits.

## Architecture

The backend is `backend/src/mis_finanzas/`: FastAPI + SQLAlchemy 2.1 + SQLite, Python 3.12, uv.
Dependencies point one way: `api → importers/reports → ledger/market → core`.
- `core/`: settings (`MIS_FINANZAS_*` env vars), engine/session, money helpers, logging, and
  the Alembic runner.
- `ledger/`: models and the pure bookkeeping logic:
  - rule matching (`rules.py`);
  - fingerprints (`dedup.py`);
  - transfer pairing (`transfers.py`).
- `importers/`: parsing is pure (bytes → `ParseResult`, no DB). `service.py` builds the preview
  and commits. Preview and commit both re-parse the upload, so the server keeps no state
  between them.
- `market/`: the FX rate source adapters, the daily refresh and the date → rate lookup.
- `reports/`: monthly and per-category totals in both currencies.

Domain rules that the code relies on:
- **Money** is `Decimal` in memory, integer cents in `transactions.amount_cents`, and decimal
  strings in JSON. FX rates use `DecimalText`. Never use float.
- **Only `income`/`expense` kinds count in totals.** `transfer` (paired rows across own
  accounts), `fx` and `investment` don't. A category's `kind` overrides the sign-based kind.
- **Dedup fingerprint** = account, date, cents, normalized description and occurrence index
  within the file. This makes overlapping exports (PDF + Excel of the same month) safe, while
  two identical same-day purchases stay distinct. A file whose sha256 was already imported is
  rejected. Originals are stored at `<data_dir>/uploads/<sha256><ext>`.
- **USD conversion** uses the MEP *sell* rate of the transaction date, or of the closest
  earlier date in the table. A row with no rate counts in `missing_rate`; it is not silently
  converted.
- Dedicated per-bank parsers (PDF statements, etc.) need real sample files. Don't write one
  from a guessed format. Until then, sources import through `importers/tabular.py` with a saved
  column mapping.

Schema changes need an Alembic migration in `migrations/versions/`. The app upgrades the DB on
startup. `tests/test_migrations.py` fails if the models and migrations drift. Generate a
revision with `command.revision(alembic_config(url), autogenerate=True, ...)` from
`core/migrate.py`, since there is no `alembic.ini`. Enums are stored by value through
`core.db.str_enum`.

The frontend is `frontend/`: React 19 + Vite + TypeScript, TanStack Query, Recharts.
- Pages live in `src/pages/`.
- `src/api/types.ts` mirrors `api/schemas.py`. Change both together.
- Every mutation goes through `useApiMutation`, which invalidates all queries.
- Navigation is hash-based (`#/movimientos`).

## Data and privacy

The data dir defaults to `~/.local/share/mis-finanzas`. It holds the SQLite DB and the original
uploads, and it is never inside the repo. `.gitignore` also blocks `samples/`, `*.db` and `.env`.
Test fixtures are synthetic. Never commit real statements, or values copied from them. Log
messages carry ids and counts, never descriptions or amounts.

## Rules in `.claude/`

The files in `.claude/rules/` load automatically:
- `just test` and `just check` must pass before a PR.
- `client-confidentiality.md`: this repo is kept apart from the owner's client work. Never
  name a client, an engagement or a work project in it.
