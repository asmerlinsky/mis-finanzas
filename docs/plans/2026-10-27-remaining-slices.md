# Remaining slices — implementation plan

Status: proposed · 2026-10-27 · builds on `docs/specs/2026-10-27-mis-finanzas-design.md`

## Context

The core is built and tested:
- the ledger;
- a generic CSV/Excel importer with saved column mappings;
- rule-based categories;
- transfer pairing;
- the daily MEP rate;
- reports in ARS and USD MEP;
- the React UI;
- `just redact` / `just preview`, which make statement samples safe to share.

What remains:
1. dedicated parsers for the owner's real statements;
2. investments (Balanz);
3. monotributo tracking;
4. getting ready for the home server.

All parsers here are designed from redacted samples in `samples/` (git-ignored). Each sample
keeps the original layout, with random digits and coded or masked names.

### Decisions taken

| Topic | Decision |
|---|---|
| Santander accounts | One app account per column and currency: CA pesos, CC pesos, CA dólares. CC only when used. |
| Visa | **Closed statement PDF only.** No parser for the "Últimos consumos" xlsx; no import of the card section inside the account statement. |
| Mercado Pago | The "resumen de cuenta" CSV (`samples/resumen-cuenta-mp.redacted.csv`), not the settlement report. |
| Balanz | Two inputs: the **movements** statement ("Cuenta Corriente por Concertación") and the **holdings** statement ("Posición consolidada"). |
| Balanz tables | Read data **only from rows under the full table header row**. Coded words (`ESPECIE_##`, `DESCRIPCION_##`) elsewhere on the page are never data. |
| Monotributo | Invoices come from ARCA's "Mis Comprobantes – Emitidos" CSV (full history, with currency and exchange rate). Invoice PDFs are attached to those rows. The owner issues Factura E in USD and Factura C in pesos. |
| Order | Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Each phase is its own branch and PR. |

## What the samples show

| Sample | Source | Shape | Quirks the parser must handle |
|---|---|---|---|
| `movimientos_cuenta.xlsx` | Santander movements export | Sheet `UltimosMovimientos`; header row (row 14 in the sample, found by its labels) `Fecha · Sucursal origen · Descripción · Referencia · Caja de Ahorro · Cuenta Corriente · Saldo` | Amounts are **text** with `.` decimal and no thousands separator (`-1904.43`). The description is `type \t detail`. Metadata above the table: `Cuenta`, `Moneda`, date range. Up to ~1000 trailing empty rows. |
| `resumen-cuenta.redacted.json` | Santander "Mi resumen" PDF, 15 pages | Sections "Movimientos en pesos" (p1–3) and "Movimientos en dólares" (p4). Header `Fecha · Comprobante · Movimiento · Caja de Ahorro en … · Cuenta Corriente en … · Saldo en cuenta` | The date appears only on the first row of a day. Each movement is 2 lines (type + 8.5pt amounts; detail line at 7pt). Signs are separate words (`-$` / `$` / `U$S`). **Invisible 0.1pt words** sit in the date column. `Saldo Inicial` row, `Saldo total` line. HTML entities in text (`mart&#237;n`). Pages 5–15 (cards, debit, investments, legal) are ignored. |
| `resumen-visa.redacted.json` | Santander Visa statement, 7 pages | p1 summary (cierre/vencimiento dates, totals ARS/USD). Tables "Pago anterior y devoluciones" (`Fecha · Descripción · Monto en pesos · Monto en dólares`) and one "Movimientos de … terminada en NNNN" per card (`Fecha · Descripción · Cuota · Comprobante · Monto en pesos · Monto en dólares`) | Inherited dates. `Cuota` like `5 de 8`. Charges are positive and payments `-$`. `Saldo anterior` rows are not movements. Pages 3–5 (taxes, interest, other cards) still need inspecting during implementation. Pages 6–7 are terms. |
| `movimientos-balanz.redacted.json` | Balanz movements, 4 landscape pages | Header `Descripción · Cant. VN · Saldo · Precio · Bruto · Arancel · Impor. IVA · Impor. Derech · Impor. IVA · Neto · Fecha Co. · Fecha Li.` repeated per page, **with different x positions per page**. Bold section title per instrument (`CEDEAR <name> - <TICKER> <code>`) or currency (`Pesos - $`, `Dólar MEP - usd`, `Dólares …`) | `Saldo Anterior` / `Saldo al d/m/yyyy` lines per section (quantity or cash balance). Operations like `Dividendo en efectivo / <TICKER>`. Dates as `d/m/yyyy`. Balanz legal footer at the page bottom. |
| `resumen-balanz.redacted.json` | Balanz holdings, 4 pages | p1: account, totals per asset class and per currency (`Pesos`, `Dólares`, `US Dollar (Cable)`). p2: tables per asset class (`Acciones`, `Cedears`) with header `Especie · Descripción · Cantidad · Garantía · Precio · Valor Actual` | `Cantidad` like `3.437,60`, `Garantía` with a `.` decimal (`0.75`), `Precio` like `$ 4.432,64`, `Valor` like `$ 761.555`. Regenerated with the fixed tool; no name left. |
| `resumen-cuenta-mp.redacted.csv` | Mercado Pago "resumen de cuenta" | Summary `INITIAL_BALANCE;CREDITS;DEBITS;FINAL_BALANCE`, blank line, then `RELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE` | Dates `dd-mm-yyyy`. Mixed number formats in the sample (`2,35` / `0.13`): confirm against a real file. `PARTIAL_BALANCE` lets the parser check every row's sign and format. |
| `comprobantes-emitidos.csv` | ARCA "Mis Comprobantes – Emitidos" | `;` delimiter, UTF-8 without BOM, 28 columns: `Fecha de Emisión` (ISO), `Tipo de Comprobante` (numeric code), `Punto de Venta`, `Número Desde/Hasta`, `Cód. Autorización`, receiver doc and name, `Tipo Cambio`, `Moneda`, the amount columns, `Imp. Total` | Amounts use a comma decimal and are **in the invoice currency**: pesos = amount × `Tipo Cambio`. Codes `19` Factura E, `20` ND E, `21` NC E, `11` Factura C, `12` ND C, `13` NC C. The per-rate IVA columns are empty for monotributo. `Imp. Total` was edited during redaction, so the sample fails the totals check on purpose. |
| `factura.redacted.json` | Invoice PDF (Factura E) | 3 identical pages (Original / Duplicado / Triplicado). Labeled fields: title and letter, `Nro: PPPPP-NNNNNNNN`, `Fecha de Emisión`, `USD - Dólar Estadounidense`, `Tipo de Cambio`, `Importe Total: USD …`, `CAE N°`, an items table | Read page 1 only. Each field has its own number format: `Tipo de Cambio: 2949.488593` (dot) and `Importe Total: USD 3907,69` (comma). `COD.` is digit-scrambled in the sample, so the title and letter decide the type. |

## Phase 0 — Redaction gaps and housekeeping (S) — done

- [x] **Truncated names and HTML entities.** Banks cut names (`gomezs`, `gome`) and
  emit entities. Changes in `tools/redaction.py`:
  - run `html.unescape` before matching;
  - mask any word that is a prefix (4+ characters) of a given name part;
  - the leak check does the same.
  - Add tests in `tests/test_redact_*.py`.
- [x] **Regenerate `resumen-cuenta.redacted.json`** with the fixed tool. It's the only sample that
  still has name fragments; the others were already redone. Re-run the name-part count; it must
  be 0 everywhere.
- [x] Delete `samples/Últimos consumos - Visa 7930.xlsx`: Visa is PDF-only, and the file still
  holds the owner's name.
- [x] **Client confidentiality:** invoices name the owner's clients. Fixtures, docs and plans use
  invented receivers only. Never copy a value from `samples/comprobantes-emitidos.csv` or the
  invoice into the repo.
- [x] **Housekeeping (the owner does these):**
  - delete `scripts/` (ad-hoc copies of the old snippets) and the stray root `package.json`,
    `package-lock.json` and `node_modules/`;
  - move the original statements out of the repo root (now git-ignored as `/*.pdf`,
    `/*.csv`…);
  - commit the current work.

## Phase 1 — Import framework v2 (M) — done

What every dedicated parser needs. Generic tabular imports keep working.

- [x] **Richer parse output** (`importers/base.py`):
  - `ParsedRow` gains `target` (a sub-account key such as `santander/CA/ARS` or
    `visa/USD`), `reference` (comprobante or reference id) and `installment` (`(5, 8)`).
  - `ParseResult` gains `metadata` (period, statement date, account label) and `checks`, a
    list of `(name, expected, actual)` totals checks.
  - **A failed check blocks the commit**, like a row error does. This is the main guard
    against a misread layout.
- [x] **Importer registry** (`importers/registry.py`): a `DedicatedImporter` protocol with
  `name`, `version`, `detect(filename, content) -> bool` and `parse(content, filename)`.
  Detection looks at the content, never only the filename. The upload endpoint accepts a
  file with no mapping and picks the importer that detects it.
- [x] **Targets map to accounts once.** A new table `source_accounts(key unique, account_id)`
  and a migration. The preview lists any unmapped targets, and the UI asks for them once.
  `ImportMapping` stays for the generic importer.
- [x] **Dedup key v2:**
  - `fingerprint = hash(account, date, cents, occurrence among identical (date, cents) in the
    file)`. The description is dropped: the xlsx and the PDF of the same Santander account
    word and split descriptions differently, while date and amount always match.
  - The rule stays correct because a statement lists every movement of its account for its
    period.
  - The Alembic migration recomputes fingerprints per import batch. On a collision it takes
    the next occurrence, so no row is lost.
  - Update `ledger/dedup.py` and CLAUDE.md.
- [x] **Near-duplicate warning:**
  - The preview marks a new row "posible duplicado" when the same account has an existing row
    with the same amount within ±3 days.
  - The commit accepts `skip_lines`, so the user can leave such rows out.
- [x] **PDF layout helpers** (`importers/pdf_layout.py`), all pure, over `PageWords`:
  - `visible(words, min_size=2)`;
  - `lines(words, tolerance)`;
  - `find_header_rows(page, labels)`, which only matches a line containing **all** labels;
  - `columns(header_row)`, giving x ranges from each label to the next;
  - `table_rows(page, header, stop)`, giving cells per column and joining continuation lines
    into the previous row;
  - `parse_signed_amount(words)` for `-$ 1.234,56`, `U$S`, `-U$S`.
- [x] **Text cleanup:** `normalize_description` also applies `html.unescape`.
- [x] Tests: unit tests per helper, and synthetic PDFs built with `tools/render_sample.build_pdf`
  at the coordinates seen in the samples.

Notes from implementing it:
- Columns are assigned per **value chunk**, not per word. Words split where the gap exceeds a
  space, and each chunk goes to the header label it overlaps most. This keeps `$ 9.000,00`
  under `Saldo` even though its `$` starts left of the label. Checked on the real Santander
  sample.
- Normalization also repairs double-encoded accents and drops invisible characters. The
  redactor masks name parts one letter off (`MARTAN` for `MARTIN`), so garbled names get masked too.
- For Phase 2: the Santander page footer (`6 - 44`) attaches to the last row of a page, so the
  parser must stop above it.

## Phase 2 — Santander (M) — done

Each parser lives in `importers/santander/` with a synthetic fixture test and a totals check.

- [x] **`santander_movements_xlsx`:**
  - Detect by the sheet name and header labels; find the header row by searching for it.
  - Targets come from the CA and CC column plus `Moneda`: `santander/CA/ARS`,
    `santander/CC/ARS`…
  - The description becomes `type detail` (tab removed); `Referencia` becomes the reference.
  - Check: where `Saldo` is present, the running balance must match.
- [x] **`santander_account_pdf`:**
  - Read only the "Movimientos en pesos" and "Movimientos en dólares" sections.
  - Group each movement's lines (type line + detail line); inherit the date; drop invisible
    words.
  - The amount's column decides its target.
  - Checks, per target: `Saldo Inicial` + Σ movements = closing balance, and each row against
    `Saldo en cuenta`.
- [x] **`santander_visa_pdf`:**
  - Targets `visa/ARS` and `visa/USD`.
  - Charges become negative (expense) and payments positive.
  - `Cuota n de m` becomes the installment, shown as ` (n/m)` in the description;
    `Comprobante` becomes the reference.
  - Leave out `Saldo anterior` rows.
  - Inspect pages 3–5 for taxes and interest sections, and include them as movements.
  - Check: Σ per currency against the statement's totals.
- [x] Transfer pairing needs no change. The bank pays the card from each account in its own
  currency, so a card payment is two transfers:
  - `Pago de tarjeta de credito` on CA pesos ↔ `Su pago en pesos` on `visa/ARS`;
  - `Pago de tarjeta de credito` on CA dólares ↔ `Su pago en usd` on `visa/USD`.
  Both pair within the 3-day window: the owner confirmed the Visa payment date equals the bank
  debit date. Each statement's payments settle the previous statement, so they pair with the
  previous month's debits.
- [ ] **Not supported:** paying the card's USD balance in pesos. The bank side is ARS and the
  card side USD, so the currency check never pairs them, and both count in totals (an expense
  and an income) until fixed by hand. The owner pays each part from the account in its own
  currency, so this is left out on purpose.

Notes from implementing it:
- The importers live in `importers/santander/` and are registered in `importers/catalog.py`.
- On the redacted samples, all three read with no row errors:
  - movements xlsx: 10 rows;
  - account PDF: 66 rows across CA pesos and CA dólares;
  - Visa PDF: 51 rows, with installments and taxes.
  Value checks fail there only because sample digits are random.
- **Verify on real files locally:** `just sample-check <folder with the real statements>`. It
  prints only counts and check results, never content.
- A Visa row with no date of its own takes the date of the row above it.

## Phase 3 — Mercado Pago (S) — done

- [x] **`mercadopago_account_csv`:**
  - Detect by the two header lines. Target `mercadopago/ARS`.
  - The description is `TRANSACTION_TYPE`; `REFERENCE_ID` becomes the reference.
  - Number format: try `,` decimal, then `.` decimal. Keep the format under which every row
    satisfies `previous PARTIAL_BALANCE + amount = PARTIAL_BALANCE` and the summary adds up;
    if none does, it's a file-level error.
- [x] `Rendimientos` lines are income, through a starter category rule shipped as a migration
  seed ("Rendimientos", kind income), which the user can edit.

Notes from implementing it:
- When neither number format satisfies the checks, the import isn't refused as unreadable.
  The comma reading is kept, so its failed checks block the commit and show which total is
  off.
- The "Rendimientos" seed (migration `0003`) also covers Santander's `Pago interes por saldo
  en cuenta`. It only inserts what's missing.
- To confirm on a real export: `sample-check` must show all four checks passing. If
  `saldos fila a fila` fails, the export probably prints money out without a minus sign.

## Phase 4 — Frontend for imports (S) — done

- [x] **Import page:**
  - Upload first; the matching importer is shown, and the generic mapping is used only when
    no importer matches.
  - The preview shows unmapped targets (pick an account or create one), failed checks in red
    (and the commit disabled), and near-duplicates with a checkbox to skip them.
- [x] Accounts page: show the `source_accounts` mapped to each account.
- [x] Types in `src/api/types.ts`, and vitest tests for the preview states.

Notes from implementing it:
- The preview panel (`pages/import/ImportPreview.tsx`) only takes props. The page wires it to
  the API; after mapping or creating an account, it re-runs the preview.
- "Crear «…»" makes the suggested account (`lib/importers.suggestedAccount`) and maps the
  target in one step.
- Near-duplicates are **imported by default** and highlighted; unticking leaves them out. A
  wrongly skipped real movement is harder to notice than a duplicate.
- Checked in headless Chrome with a synthetic Santander statement: detect, all checks green,
  blocked until mapped, create accounts, import 4 rows, mappings on Accounts, re-upload blocked.

## Phase 5 — Investments (Balanz) (L) — done

New package `investments/`, importing `core`, `ledger` and `market`. Importers import its
record types; it imports nothing from `importers`. Split in two steps, because valuation is
only worth building on parsers verified against real statements:
- **5a — data in:** models, both parsers, the import flow, the preview.
- **5b — valuation:** daily prices, valuation, the "Inversiones" page.

What the samples show, beyond the table in "What the samples show":
- Movements:
  - Two groups, each under its own heading above the header row: `Instrumentos` and
    `Monedas`. A group and its last section carry over to the next page, which starts with a
    header row and no title.
  - The header has `Impor. IVA` **twice** (IVA on the fee, IVA on the market rights), so
    header matching must accept a repeated label.
  - Instrument quantities are in `Cant. VN`; cash balances are in `Neto`.
  - `Saldo al <date>` lines are running balances after each day; the last one closes the
    section.
  - A CEDEAR dividend shows twice: the amount, positive, in the dollar section; its fees,
    negative, in `Pesos`.
- Holdings:
  - Page 1 prints two side-by-side columns: class totals under `Instrumentos` and currency
    totals under `Monedas`.
  - `Valor Actual` is in whole pesos.
- data912: `/live/arg_cedears`, `/live/arg_stocks`, `/live/arg_bonds` and `/live/arg_corp`
  return whole panels with `symbol` and last price `c`. Bonds are quoted per 100 nominal;
  the `D` / `C` suffixes are the MEP / cable lines.

### 5a — data in — done

- [x] **`pdf_layout`:** a label listed twice matches its second occurrence, as column
  `Impor. IVA (2)`.
- [x] **Model and migration:**
  - `Instrument(ticker unique, name, asset_class, broker_code)`.
  - `InvestmentOperation(instrument, trade_date, settle_date, description, quantity, price,
    gross, fees, net, fingerprint unique, import_batch)`. Its amounts are decimals as
    printed, because the instrument section doesn't name the currency.
  - `HoldingSnapshot(broker, as_of, source, import_batch)`, unique on `(broker, as_of,
    source)`. `source` is `tenencias` (holdings) or `movimientos` (the closing quantities of
    a movements statement). A later file for the same key replaces the snapshot.
  - `HoldingPosition(snapshot, instrument, quantity, price, value, currency)`. Price and value
    are empty in `movimientos` snapshots.
  - `HoldingCash(snapshot, label, currency, amount)`.
  - Seed a `Dividendos` income category with the rule `DIVIDENDO`. CEDEAR dividend fees in
    pesos then reduce dividend income instead of counting as expenses.
- [x] **`balanz_movements_pdf`:**
  - Detect by the title `Cuenta Corriente por Concertación` and the 12-label header.
  - Read rows only under a header row. Stop at a heading (bigger text) or the legal footer.
    A bold row that has only a description is a section title.
  - `Monedas` sections become ledger rows, dated `Fecha Co.` (the statement's balances run
    by trade date), with amount `Neto`. Targets:
    - `Pesos` → `balanz/ARS`;
    - `Dólar MEP` → `balanz/MEP/USD`;
    - any other `Dólar…` section → `balanz/<rest of title>/USD`.
  - `Instrumentos` sections become operations: title `<name> - <TICKER> <code>`, quantity
    from `Cant. VN`, fees = the four fee columns.
  - The closing quantity of each instrument becomes a `movimientos` snapshot at the period
    end.
  - **Checks:**
    - every section has `Saldo Anterior` and a final `Saldo al`;
    - each `Saldo al` equals the running balance, for cash and for quantities.
- [x] **`balanz_holdings_pdf`:**
  - Detect by `Posición consolidada` and the 6-label header.
  - Asset class = the heading above each header row.
  - `as_of` = `Fecha resumen`; the page-1 `Cuenta` field (a name) is never read.
  - Cash comes from page 1, `Monedas` column.
  - **Check:** Σ `Valor Actual` per class = the page-1 class total, within 1 peso per row,
    because each value is rounded.
- [x] **Import flow:**
  - `ParseResult.investments` carries the records.
  - The preview shows positions, cash lines and new operations.
  - The commit stores them in the same transaction as the ledger rows.
  - A holdings file has no ledger rows, and can still be committed.
  - Operations dedupe by fingerprint (broker, ticker, trade date, quantity, net, occurrence).
- [x] **`sample_check`** also reports positions, cash lines and operations, as counts only.

**Trades (verified on two more samples, `resumen_balanz_febrero` / `_junio`, and on the
real statements: no row errors, every check passes):**
- A trade prints `Boleto / <n> / COMPRA / <n> / <TICKER> / <usd|$>` in the instrument section
  (quantity, price with 10 decimals, gross, fees, net) and again in each currency section it
  moves (cash). Funds print `Liquidación de Suscripción / …` and `Transferencia a … de FCI`.
- An instrument's intermediate `Saldo al <date>` may print with no quantity; it is skipped.
- Long amounts in adjacent columns print with no gap and extract as one word
  (`145.769,874432,25`). The movements parser splits them back (2 decimals, or 10 for a
  price), and `pdf_layout.chunks` never joins two amounts into one cell.
- Values start where their column's label starts and overrun toward the next label, so a
  value overlapping two labels about equally went to the wrong one. `pdf_layout` now gives a
  value to the label it starts in. Every earlier sample parses identically after the change.
- Migration 0007 seeds `Inversiones` (kind `investment`) with anchored regex rules for
  `Boleto / n / COMPRA|VENTA` and `Liquidación de Suscripción|Rescate`, so trades don't count
  as expenses. `VENTA` and `Rescate` are not in a sample yet.

### 5a — data in — done

- [x] **`pdf_layout`:** a label listed twice matches its second occurrence, as column
  `Impor. IVA (2)`.
- [x] **Model and migration:**
  - `Instrument(ticker unique, name, asset_class, broker_code)`.
  - `InvestmentOperation(instrument, trade_date, settle_date, description, quantity, price,
    gross, fees, net, fingerprint unique, import_batch)`. Its amounts are decimals as
    printed, because the instrument section doesn't name the currency.
  - `HoldingSnapshot(broker, as_of, source, import_batch)`, unique on `(broker, as_of,
    source)`. `source` is `tenencias` (holdings) or `movimientos` (the closing quantities of
    a movements statement). A later file for the same key replaces the snapshot.
  - `HoldingPosition(snapshot, instrument, quantity, price, value, currency)`. Price and value
    are empty in `movimientos` snapshots.
  - `HoldingCash(snapshot, label, currency, amount)`.
  - Seed a `Dividendos` income category with the rule `DIVIDENDO`. CEDEAR dividend fees in
    pesos then reduce dividend income instead of counting as expenses.
- [x] **`balanz_movements_pdf`:**
  - Detect by the title `Cuenta Corriente por Concertación` and the 12-label header.
  - Read rows only under a header row. Stop at a heading (bigger text) or the legal footer.
    A bold row that has only a description is a section title.
  - `Monedas` sections become ledger rows, dated `Fecha Co.` (the statement's balances run
    by trade date), with amount `Neto`. Targets:
    - `Pesos` → `balanz/ARS`;
    - `Dólar MEP` → `balanz/MEP/USD`;
    - any other `Dólar…` section → `balanz/<rest of title>/USD`.
  - `Instrumentos` sections become operations: title `<name> - <TICKER> <code>`, quantity
    from `Cant. VN`, fees = the four fee columns.
  - The closing quantity of each instrument becomes a `movimientos` snapshot at the period
    end.
  - **Checks:**
    - every section has `Saldo Anterior` and a final `Saldo al`;
    - each `Saldo al` equals the running balance, for cash and for quantities.
- [x] **`balanz_holdings_pdf`:**
  - Detect by `Posición consolidada` and the 6-label header.
  - Asset class = the heading above each header row.
  - `as_of` = `Fecha resumen`; the page-1 `Cuenta` field (a name) is never read.
  - Cash comes from page 1, `Monedas` column.
  - **Check:** Σ `Valor Actual` per class = the page-1 class total, within 1 peso per row,
    because each value is rounded.
- [x] **Import flow:**
  - `ParseResult.investments` carries the records.
  - The preview shows positions, cash lines and new operations.
  - The commit stores them in the same transaction as the ledger rows.
  - A holdings file has no ledger rows, and can still be committed.
  - Operations dedupe by fingerprint (broker, ticker, trade date, quantity, net, occurrence).
- [x] **`sample_check`** also reports positions, cash lines and operations, as counts only.

**Not verified:** the sample month has no buys or sells, so an operation row's wording and
the quantity's sign are untested. The quantity checks would block a misread. Confirm on a real
statement with a trade. Then decide on a rule that gives trade cash rows the `investment`
kind, which until then count as expense or income.

Notes from implementing it:
- Records live in `investments/records.py`, tables in `investments/models.py`, writing in
  `investments/store.py`. The parsers live in `importers/balanz/`.
- `Check` gained a `tolerance`, used only by the holdings class totals.
- On the redacted samples, both read with no row errors:
  - movements: 22 cash rows (11 `balanz/ARS`, 11 in the dollar section) and 15 instruments;
  - holdings: 18 positions (2 Acciones, 16 Cedears) and 3 cash lines.
  Value checks fail there only because sample digits are random.
- **Verify on real files locally:** `just sample-check <folder>`. It now also prints the number
  of operations, positions and cash lines.
- The sample's third currency section is redacted, so its target is built from its title.
  Expect something like `balanz/CABLE/USD` on a real file.

### 5b — valuation — done

- [x] **Daily prices:**
  - Add `data912.com` to `public_hosts`.
  - A `PriceSource` fetches the four whole panels once a day and stores
    `InstrumentPrice(symbol, date, price, source)`. It never requests one ticker.
  - Price history starts on the day fetching starts.
- [x] **Valuation:**
  - Quantity: the latest snapshot, plus later operations.
  - Value: quantity × the latest price × factor. The factor comes from the latest
    `tenencias` snapshot, `value / (quantity × price)`: about 1 for shares and CEDEARs, about
    0.01 for bonds quoted per 100. It is 1 when there is no holdings statement.
  - Cash comes from the latest holdings statement's currency lines. The ledger has no
    opening balance for the broker accounts, so their rows don't add up to the cash held.
  - Everything is shown in ARS and USD MEP.
- [x] **UI: "Inversiones" page:**
  - total value with a date;
  - allocation by asset class;
  - a positions table with quantity, price, value and the snapshot it comes from;
  - dividends received per month, from the `Dividendos` category.
- [ ] **Later:** cost basis and returns. They need the full operations history, which only
  builds up as statements are imported.

Notes from implementing it:
- Prices: `market/prices.py` (`Data912PanelsSource`, `upsert_prices`, `latest_prices`). The
  daily refresh runs it after the MEP rate, through the same fetch log. Every symbol of the
  four panels is stored, under the download day. A test checks that only the four panel URLs
  are ever requested.
- Valuation: `investments/valuation.py`; API `GET /api/investments/portfolio` and
  `GET /api/investments/dividends?start&end` (net of fees, from the `Dividendos` category).
- Each price shows where it came from: `mercado` (the panel) or `resumen` (the statement,
  when no newer market price exists).
- Checked in headless Chrome with the synthetic statements, in light mode, dark mode and at
  phone width: totals, allocation, positions with their price source, cash, and dividends per
  month.
- **To confirm on real data:** the day after the first refresh, compare the page's total with
  Balanz's own valuation.

## Phase 6 — Monotributo (M)

New package `monotributo/`, importing `core` only. Invoices come from the Mis Comprobantes
export; PDFs are attached to them.

- [ ] **Model and migration:**
  - `Invoice(type_code, point_of_sale, number_from, number_to, issued_on, cae,
    receiver_doc_type, receiver_doc, receiver_name, currency, fx_rate, net_taxed,
    net_untaxed, exempt, other_taxes, vat, total, total_ars, import_batch_id, pdf_path)`.
  - Money is in cents; `fx_rate` uses `DecimalText`.
  - Unique key `(type_code, point_of_sale, number_from)`.
  - `total_ars = total × fx_rate`, negative for credit notes.
- [ ] **`importers/arca/mis_comprobantes.py`** (pure):
  - Detection: the header has `Tipo de Comprobante`, `Punto de Venta`, `Cód. Autorización` and
    `Imp. Total`.
  - Columns are mapped **by header name**, not position, so ARCA adding columns doesn't break
    it.
  - Unknown type codes are row errors.
  - **Check per row:** `Imp. Total` = Σ components, otherwise it's a row error.
- [ ] **Import service** (`monotributo/service.py`):
  - Preview and commit, reusing the upload, sha256 and stored-original handling.
  - Re-importing a newer export updates existing invoices by the unique key, so the full
    history can be loaded again at any time. The preview lists rows whose fields changed.
- [ ] **Invoice PDFs as attachments** (`importers/arca/invoice_pdf.py`):
  - Reads only identity and totals from page 1: type from the title and letter, point of sale
    and number, date, currency, fx rate, `Importe Total`, CAE.
  - The upload links the stored PDF to the matching invoice.
  - **Check:** the PDF's total, rate and CAE must equal the invoice's, otherwise it's rejected.
  - A PDF with no matching invoice is rejected with "importá primero Mis Comprobantes".
- [ ] **Categories:** a versioned seed file `monotributo/categories.json`.
  - Fields: category letter, annual gross-income cap, monthly payment for services, and
    `valid_from`.
  - ARCA updates it twice a year; the owner edits the file.
  - The UI shows "tabla vigente desde …".
- [ ] **Profile:** the owner's current category and activity (services), stored in a `profile`
  table and editable in the UI.
- [ ] **Status** (`monotributo/status.py`, pure):
  - rolling 12-month Σ `total_ars` against the current category's cap, and the margin left;
  - the category implied by the last 12 months at the next recategorization (January/July);
  - warnings at 80%, 90% and 100%.
- [ ] **API and UI:**
  - `GET /api/monotributo/status`, `GET /api/monotributo/invoices`, plus the import endpoints;
  - a "Monotributo" page with the status card, a monthly invoicing chart (ARS, with USD as
    invoiced) and the invoice list with an "adjuntar PDF" button.
- [ ] **Tests**, with synthetic data and invented receivers only:
  - CSV parsing (codes, credit-note sign, comma decimals, header-by-name, extra columns);
  - the total check;
  - updating existing invoices on re-import;
  - PDF identity extraction, from a synthetic PDF built with `tools/render_sample.build_pdf`;
  - PDF matching;
  - status math across a recategorization boundary.

## Phase 7 — Home server readiness (M)

- [ ] **Single-user login:**
  - argon2 password hash in the data dir, session cookie, every `/api` route protected.
  - Binding to anything other than `127.0.0.1` is refused unless login is configured.
- [ ] **Docker:** a multi-stage `Dockerfile` (node build → python runtime), and `compose.yaml`
  with the data dir as a volume and a healthcheck.
- [ ] **Backups:** a nightly `sqlite3 .backup` plus `uploads/`, copied to a configurable folder.
- [ ] **Docs:** reach the server over Tailscale or WireGuard, never through router port
  forwarding.

## Verification (per phase)

- `just test` and `just check` pass. Every parser has a synthetic fixture test covering:
  layout, inherited dates, continuation lines, signs, and totals checks that pass and fail.
- **`just sample-check`** (new, Phase 1): runs every importer over `samples/` and prints, per
  file, the importer detected, the row count per target, and each check's pass/fail. It
  never prints row content. It is a local command, not a test, because `samples/` isn't in
  the repo.
- Manual run with real files (`just serve`), for each statement:
  1. Import it.
  2. Confirm the checks pass and the targets map to the right accounts.
  3. Re-import an overlapping file (e.g. the Santander xlsx after the PDF): it must add 0 rows.
  4. Confirm card payments pair as transfers.
  5. Confirm the dashboard totals and the investments value match the statements.
- Privacy: after Phase 5, outbound connections still go only to the allowlisted hosts (now
  ArgentinaDatos and data912), checked with `ss -tp` while the app runs a refresh.
