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
- [ ] (Open) Transfer pairing needs no change. A card payment from the bank (`Pago de tarjeta de
  credito`) and `Su pago en pesos` on `visa/ARS` pair if they're within 3 days of each other.
  Measure the gap on real data, and widen the window to 7 days for card accounts only if
  needed.

Notes from implementing it:
- The importers live in `importers/santander/` and are registered in `importers/catalog.py`.
- On the redacted samples, all three read with no row errors:
  - movements xlsx: 10 rows;
  - account PDF: 66 rows across CA pesos and CA dólares;
  - Visa PDF: 51 rows, with installments and taxes.
  Value checks fail there only because sample digits are random.
- **Verify on real files locally:** `just sample-check <folder with the real statements>`. It
  prints only counts and check results, never content.
- The Visa statement prints no date on payment rows; they take the `Saldo anterior` row's date.
  The pairing window question stays open until it's measured on real data.

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

## Phase 5 — Investments (Balanz) (L)

New package `investments/`, importing `core` and `ledger` (for the broker cash accounts).

- [ ] **Model and migration:**
  - `Instrument(ticker, name, asset_class, broker_code)`;
  - `Operation(account, instrument, kind, trade_date, settle_date, quantity, price, gross,
    fees, net, currency, reference)`, where kind is compra, venta, dividendo, renta,
    amortización, suscripción, rescate or otro;
  - `HoldingSnapshot(account, as_of)`, with `Position(instrument, quantity, price, value)` and
    `CashBalance(currency, amount)`;
  - `InstrumentPrice(ticker, date, price, source)`.
- [ ] **`balanz_movements_pdf`:**
  - For each page, take the header row containing all 12 labels, so the column x positions
    are read from that page. Rows are read only below that header.
  - A bold title line starts a section: an instrument (`… - TICKER code`) or a currency
    (`Pesos`, `Dólar MEP`, `Dólares …`).
  - Instrument sections give operations plus `Saldo al` quantities. **Check:**
    `Saldo Anterior` + Σ quantities = `Saldo al`.
  - Currency sections give cash rows. They become ledger transactions on the broker cash
    accounts (targets `balanz/ARS`, `balanz/USD-MEP`, `balanz/USD-CABLE`): a dividend is
    income, a buy or sell is `investment`, and a fee is part of `net`.
  - Everything outside a section and its header (page header, `Comitente`, legal footer) is
    ignored, **including coded words**.
- [ ] **`balanz_holdings_pdf`:**
  - Only rows under a header row containing all of `Especie · Descripción · Cantidad · Garantía
    · Precio · Valor Actual`.
  - The asset class is the section title above (`Acciones`, `Cedears`, …).
  - Cash comes from the page-1 `Monedas` block.
  - **Check:** Σ `Valor Actual` per class = the page-1 class totals.
- [ ] **Daily prices:**
  - Add `data912.com` to `public_hosts`.
  - A `PriceSource` adapter fetches the **whole** live panels (`/live/arg_cedears`,
    `/live/arg_stocks`, `/live/arg_bonds`) once a day and stores every row. It never requests
    one ticker.
  - Price history starts on the day fetching starts; earlier dates are valued only at
    statement snapshots.
- [ ] **Valuation and returns:**
  - Value per day = quantity (from the latest snapshot, adjusted by later operations) ×
    the latest price.
  - Cost basis is the weighted average from operations.
  - Portfolio return = change in value − net contributions, where net contributions are
    ledger transfers into or out of the broker accounts.
  - Everything is shown in ARS and USD MEP.
- [ ] **UI: "Inversiones" page** with:
  - value over time;
  - allocation by asset class;
  - a positions table with quantity, price, value, cost and result;
  - dividends received.

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
