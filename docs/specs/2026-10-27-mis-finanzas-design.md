# mis-finanzas — design

## Context

The repo is empty: a README and the `.claude/` rules. The owner wants a personal finance app
with a server and a web frontend to:
- track earnings, expenses and investments;
- import statements from Santander Río, Mercado Pago and Balanz;
- track their monotributo status with ARCA, using the invoices they issue.

**Hard constraint:** all personal data is processed and stored locally. The app makes no
outbound call that carries personal data. It may download *public* data (FX rates, prices) at
most once a day.

The app is four sub-projects on one shared core. This plan designs the core and the first slice
(spending) in detail, and leaves the later slices as outlines.

## Decisions (from Q&A)

| Topic | Decision |
|---|---|
| Hosting | Runs on the laptop (localhost) now. Must move to an always-on home server later without rework. |
| Stack | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + SQLite; React + Vite + TypeScript frontend. |
| Data at rest | Plain SQLite and the original files, in a data dir **outside the repo**. Protection comes from full-disk encryption. |
| Currency | Every amount and total in nominal ARS and in USD at the daily MEP rate, side by side. |
| Categories | Manual assignment that creates rules ("description contains X → category Y"). Rules apply on import. No ML, no LLM. |
| Tax | Monotributista. Invoices come from the ARCA "Mis Comprobantes" export. No ARCA web services. |
| Santander inputs | Movement exports (Excel/CSV), credit card statement PDFs, account statement PDFs. These overlap, so imports must deduplicate. |
| Investments | CEDEARs/stocks, bonds/ONs/Letras, USD at the broker. Coupons only as received payments; no projected schedules. |
| Build order | Core → Santander + Mercado Pago spending → monotributo → Balanz investments. |
| Samples | None yet. Importers are designed against documented formats, with a generic column-mapping importer usable from day one. |

## Architecture

```
mis-finanzas/
  backend/                       uv project, package `mis_finanzas`
    src/mis_finanzas/
      core/        config, db session, money (Decimal), logging
      ledger/      accounts, transactions, categories, rules, transfers, dedup
      importers/   Importer protocol + registry; generic_tabular, later per-source parsers
      market/      PublicHttpClient (host allowlist), FX/price sources, daily refresh
      api/         FastAPI routers, Pydantic schemas
      main.py      app factory
    migrations/    Alembic
    tests/         pytest; synthetic fixtures only
  frontend/                      React + Vite + TS, TanStack Query, Recharts
  justfile                       setup, dev, test, check, format
  docs/specs/                    design doc
```

The server binds to `127.0.0.1` by default. Config comes from environment variables / `.env`:
`MIS_FINANZAS_DATA_DIR` (default `~/.local/share/mis-finanzas`, holding `finanzas.db` and
`uploads/`), host and port. In production FastAPI serves the built frontend, so the move to a
home server is one container plus a mounted data dir. Login is **not in v1**. It becomes
required before the server binds to anything other than localhost.

## Domain model (v1)

- **Account:** institution, kind (`bank | card | wallet | broker`), currency (`ARS | USD`).
- **Transaction:** account, date, amount as a `Decimal` (stored as integer cents, never float),
  currency, raw and normalized description, category, kind
  (`income | expense | transfer | fx | investment`), `import_batch_id`, `fingerprint`.
- **Category / CategoryRule:** rule = match on normalized description (contains / regex),
  optional account and amount sign; the first match by priority wins.
- **ImportBatch:** source, importer name and version, file `sha256`, stored original path,
  status, row counts.
- **FxRate:** date, type (`MEP`), buy/sell, source.

Ledger rules that keep totals correct:
- **Transfers between own accounts are not income or expense.** The app pairs them
  (opposite amounts in two of your accounts within ±3 days) and offers each pair for one-click
  confirmation. Buying MEP is `fx`, not an expense.
- **Credit cards:** each charge (including each installment as it posts) is an expense on the
  card account. Paying the card from the bank is a transfer, which avoids double counting.
- **Deduplication:** the same file hash is rejected. Rows get
  `fingerprint = hash(account, date, amount, normalized_description, occurrence_index)`, so
  overlapping PDF and Excel imports don't duplicate.
- **USD view:** amount ÷ the MEP rate of the transaction date, or the closest earlier business
  day. Rates are stored, never recomputed from live data.

## Import flow

Upload → detect the importer → parse to `ParsedTransaction`s (pure, no DB) → **preview** that
shows duplicates, suggested categories, transfer candidates and per-row parse errors → confirm
→ write everything in one DB transaction → store the original under `uploads/<sha256>`.
Nothing is written on parse failure.

Importers implement `detect(file) -> bool` and `parse(file) -> ParseResult`. v1 ships the
**generic tabular importer**: CSV or Excel plus a saved column mapping per source (date, amount
or debit/credit, description, date format, decimal separator `1.234,56`). With it, Santander
and Mercado Pago exports work before any dedicated parser exists. Dedicated parsers (Santander
card PDFs via `pdfplumber`, Mercado Pago reports, Mis Comprobantes, Balanz) are added once real
sample files exist. They are not guessed.

## Public data (outbound network)

- All outbound HTTP goes through one `PublicHttpClient`: GET only, host allowlist in config,
  timeouts, no cookies or credentials. A test asserts that any other host is rejected.
- Requests fetch **whole market panels, never one ticker**, so a provider can't infer holdings.
- Daily refresh: on startup and on a once-a-day schedule, skipped if the fetch log already has
  a run today.
  - v1 fetches the MEP rate (candidate source: data912 `/live/mep`; historical backfill source
    to be verified at implementation time).
  - If the fetch fails, the app logs it, keeps the last known rate and marks the UI "stale
    since <date>".
- Every source is unofficial and could break, so each is an adapter behind a
  `RateSource`/`PriceSource` protocol.

## Frontend (v1)

- **Dashboard:** monthly income versus expenses and by-category breakdown, in ARS and USD MEP.
- **Transactions:** filter, edit, recategorize, "create rule from this".
- **Import:** upload, mapping setup for new sources, preview, confirm.
- **Accounts and Categories/Rules:** CRUD pages.

## Later slices (outline only, each gets its own spec)

- **Monotributo:**
  - Import Mis Comprobantes as Invoice records.
  - Compare rolling 12-month invoiced income with the category limits.
  - Show recategorization dates (January/July) and the margin left.
  - Category limit tables are public: download them from ARCA's site, or update them by hand.
- **Balanz investments:**
  - Instruments, trades and positions from the movement and holdings exports.
  - Daily price snapshots from the whole-panel CEDEAR/bond downloads.
  - Coupons and amortizations recorded as income from the movements.
  - Value and returns in ARS and USD MEP.

## Build steps

1. **Spec and repo setup:**
   - Write this design to `docs/specs/2026-10-27-mis-finanzas-design.md`.
   - Add a `.gitignore` covering the data dir, `samples/`, `.env`, `node_modules`, build output.
   - Scaffold backend (uv, ruff, mypy, pytest) and frontend (Vite React TS, eslint, vitest).
   - Add a `justfile` (`setup`, `dev`, `test`, `test-file`, `check`, `format`).
   - Update `CLAUDE.md` and `.claude/rules/coding-rules.md` with the real structure and
     commands, plus a frontend section.
2. **Core backend:**
   - Config, DB and Alembic, the ledger model.
   - Rule-based categorization, transfer pairing, dedup.
   - Generic tabular importer with saved mappings.
   - `PublicHttpClient` and daily MEP refresh.
   - API endpoints.
3. **Frontend v1:** the five pages above, wired to the API.
4. Later, each as its own spec: dedicated Santander/Mercado Pago parsers (needs samples),
   monotributo, Balanz.


## Verification

- `just test`:
  - unit tests for money/FX conversion, rule matching, dedup fingerprints, transfer pairing,
    generic importer (`1.234,56` amounts, debit/credit columns, bad rows);
  - API tests with a temp SQLite DB;
  - a `PublicHttpClient` allowlist test.
- `just check`: ruff, mypy, eslint, `tsc --noEmit`.
- Manual end-to-end:
  - `just dev`, create accounts, upload a synthetic CSV.
  - Map its columns and check the preview, then import.
  - Re-upload the same file and confirm it is rejected.
  - Recategorize a row and create a rule; the next import applies it.
  - Confirm the dashboard shows ARS and USD MEP.
  - Kill the network and confirm the stale-rate banner appears.
- Privacy check: with the app running, confirm that outbound connections go only to the
  allowlisted host (e.g. `ss -tp`, or the client's request log).
