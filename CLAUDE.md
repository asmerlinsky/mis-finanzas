# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mis-finanzas` is a personal finance app for one owner in Argentina:
- a ledger of earnings and expenses;
- statement imports from the owner's bank, wallet and broker;
- every total shown in ARS and in USD at the daily MEP rate;
- broker investments: Balanz statements, valued daily with public market prices;
- monotributo: invoices from ARCA's "Mis Comprobantes" export, with their PDFs, against the
  category caps.

The design and its decisions are in `docs/specs/2026-10-27-mis-finanzas-design.md`, and the
slices after it in `docs/plans/2026-10-27-remaining-slices.md`. Read it before starting a new slice. The UI and
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
just redact <file> --name "…"   # redacted sample of a statement into samples/ (xlsx/csv/pdf)
just preview samples/x.redacted.json   # render a PDF words sample back to a PDF
just sample-check               # run every importer over samples/: counts and checks only
just password                   # set the login password (required to listen beyond localhost)
just backup [folder]            # back up the DB and uploads now (default MIS_FINANZAS_BACKUP_DIR)
docker compose up -d --build    # home server; setup in docs/home-server.md
# Sample digits are random, so value checks fail on samples. To verify checks, run the
# recipe on a folder of real statements: it prints counts and pass/fail only.
cd backend && uv run python -m mis_finanzas.tools.sample_check <folder>
```

Node comes from `n` (`/usr/local/bin/node`, v22). The apt `/usr/bin/node` v12 is too old.
`rm -rf` and `git commit` are denied in `.claude/settings.json`. The owner commits.

## Architecture

The backend is `backend/src/mis_finanzas/`: FastAPI + SQLAlchemy 2.1 + SQLite, Python 3.12, uv.
Dependencies point one way:
`api → importers/reports → investments/monotributo → ledger/market → core`.
- `core/`: settings (`MIS_FINANZAS_*` env vars), engine/session, money helpers, logging, the
  Alembic runner, and the daily backup (`backup.py`).
- `auth/`: single-user login. The password's argon2 hash is in `<data_dir>/auth.json`;
  sessions are server-side, stored as token hashes. `api/auth_guard.py` makes every `/api`
  route except health and `/api/auth/*` need a session once a password exists, and
  `__main__.py` refuses to listen beyond localhost without one.
- `ledger/`: models and the pure bookkeeping logic:
  - rule matching (`rules.py`);
  - fingerprints (`dedup.py`);
  - transfer pairing (`transfers.py`);
  - rule suggestions (`suggestions.py`): uncategorized movements grouped by merchant key.
    `reports/rule_suggestions.py` ranks them in pesos and counts what each rule would catch
    (`GET /api/rules/suggestions`, `GET /api/rules/preview`).
- `importers/`: parsing is pure (bytes → `ParseResult`, no DB). `service.py` builds the preview
  and commits. Preview and commit both re-parse the upload, so the server keeps no state
  between them.
  - A file is read either by a saved column mapping (`tabular.py`, one account), or by the
    one dedicated importer in `registry.py` that recognizes it by content.
  - Dedicated importers emit rows with a `target` (`santander/CA/ARS`). Each target is
    mapped once to an account (`source_accounts`); an unmapped target blocks the commit.
  - They also emit `checks` (statement totals against parsed sums). A failed check blocks the
    commit: it means the layout was misread.
  - Importers live in a package per institution (`importers/santander/`) and are registered
    in `importers/catalog.py`.
  - Santander card statements (Visa, Amex, and the Visa section of the account statement)
    share one reader, `santander/card_statement.py`, configured by a `CardLayout`.
  - PDF importers work on `PageWords` (`pdf_words.py`), so they also run on the redacted JSON
    samples. Use `pdf_layout.py` to read tables: header rows need **all** labels, so data is
    only read under the right table.
- `tools/`: the redaction, preview and sample-check commands. Nothing in the app imports it.
- `investments/`: instruments, operations and holdings snapshots from broker statements.
  Parsers emit its plain records (`records.py`); `store.py` writes them in the import's
  transaction. Broker cash is ledger rows on the broker's accounts, not here.
- `monotributo/`: issued invoices (upserted by type, point of sale and number), the owner's
  category, ARCA's category tables (`categories.json`, edited by hand twice a year) and the
  status math (`status.py`, pure). It imports `core` only.
- `market/`: the FX rate and price source adapters (ArgentinaDatos MEP, data912 panels), the
  daily refresh and the date → rate lookup.
- `reports/`: monthly and per-category totals in both currencies.

Domain rules that the code relies on:
- **Money** is `Decimal` in memory, integer cents in `transactions.amount_cents`, and decimal
  strings in JSON. FX rates use `DecimalText`. Never use float.
- **Only `income`/`expense` kinds count in totals.** `transfer` (paired rows across own
  accounts), `fx` and `investment` don't. A category's `kind` overrides the sign-based kind.
  - Transfers pair only within one currency. Paying a card's USD balance in pesos is **not
    supported**: both sides stay unpaired and count in totals.
- **Dedup fingerprint** (v2) = account, date, cents and occurrence index among rows with the
  same date and amount in the file. There is **no description**, because two exports of one
  account word it differently. Overlapping files (the Excel and the PDF of the same month)
  dedupe, while two identical same-day purchases stay distinct.
  - A new row whose account has the same amount within ±3 days is flagged
    `near_duplicate`; the commit takes `skip_lines` to leave such rows out.
  - A file whose sha256 was already imported is rejected. Originals are stored at
    `<data_dir>/uploads/<sha256><ext>`.
- **Descriptions are normalized** by `ledger/text.normalize_description`: HTML entities
  decoded, double-encoded accents repaired, invisible characters dropped, accents stripped,
  uppercased. Banks emit all of these.
- **USD conversion** uses the MEP *sell* rate of the transaction date, or of the closest
  earlier date in the table. A row with no rate counts in `missing_rate`; it is not silently
  converted.
- Dedicated per-bank parsers need a redacted sample in `samples/`. Never write one from a
  guessed format, and never copy a sample's values into the repo; fixtures are synthetic.
  Until a parser exists, a source imports through `importers/tabular.py` with a saved column
  mapping.

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
messages carry ids and counts, never descriptions or amounts. Backups copy the DB and uploads,
never `auth.json`. The Docker build context is an allowlist (`.dockerignore`), so `samples/`
and data folders can't enter an image.

## Rules in `.claude/`

The files in `.claude/rules/` load automatically:
- `just test` and `just check` must pass before a PR.
- `client-confidentiality.md`: this repo is kept apart from the owner's client work. Never
  name a client, an engagement or a work project in it.
