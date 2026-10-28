# Coding Rules

## Python

- Functions MUST NOT exceed 50 lines. Break into smaller helpers.
- NEVER define functions inside other functions. Extract to module/class level.
- NEVER add `# noqa` without explicit documented justification.
- Refactor functions triggering C901 or PLR0915 into smaller functions.
- Line length max 100 chars.
- Import order: stdlib -> third-party -> first-party -> local.
- Use `logger.info/error` not `print()`.
- No bare `except: pass` — log or re-raise.

## Structure

- **Dependencies point one way:** `api → importers/reports → investments/monotributo → ledger/market → core`. `core/`
  imports nothing from the app. `ledger/` and `market/` don't import each other. `api/` only
  translates HTTP to service calls, and the logic lives in the modules below it.
- **Parsing is pure:** an importer turns bytes into a `ParseResult` with no database access.
  Database work happens in `importers/service.py`.
- **All outbound HTTP goes through `PublicHttpClient`.** Never create another HTTP client, and
  never send personal data or per-holding queries.
- **Money is `Decimal`/integer cents**, never float, from parsing through to the API.
- **Schema changes come with an Alembic migration.** `tests/test_migrations.py` must keep
  passing.

## Frontend (TypeScript)

- `src/api/types.ts` mirrors the backend schemas. Change it in the same commit.
- Server state lives in TanStack Query, and mutations use `useApiMutation`. Don't copy server
  data into component state.
- Amounts arrive as decimal strings. Format them with `lib/format.ts` (`es-AR`), and don't do
  arithmetic on them beyond display totals.

## Quality Commands

```bash
just check              # All quality checks
just format             # Auto-format code
just lint               # Run linters
```
