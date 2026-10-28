// Mirrors backend/src/mis_finanzas/api/schemas.py. Amounts are decimal strings.

export type AccountKind = 'bank' | 'card' | 'wallet' | 'broker'
export type Currency = 'ARS' | 'USD'
export type TransactionKind = 'income' | 'expense' | 'transfer' | 'fx' | 'investment'
export type MatchType = 'contains' | 'regex'
export type AmountSign = 'any' | 'debit' | 'credit'

export interface AccountInput {
  name: string
  institution: string
  kind: AccountKind
  currency: Currency
}

export interface Account extends AccountInput {
  id: number
}

export interface CategoryInput {
  name: string
  kind: TransactionKind | null
}

export interface Category extends CategoryInput {
  id: number
}

export interface RuleInput {
  category_id: number
  pattern: string
  match_type: MatchType
  account_id: number | null
  sign: AmountSign
  priority: number
}

export interface Rule extends RuleInput {
  id: number
}

export interface Transaction {
  id: number
  account_id: number
  account_name: string
  currency: Currency
  date: string
  amount: string
  description: string
  category_id: number | null
  category_name: string | null
  kind: TransactionKind
  transfer_pair_id: number | null
  import_batch_id: number | null
}

export interface TransactionPage {
  items: Transaction[]
  total: number
}

export interface TransactionFilters {
  account_id?: number
  kind?: TransactionKind
  search?: string
  uncategorized?: boolean
  start?: string
  end?: string
  offset?: number
  limit?: number
}

export interface TransferCandidate {
  outgoing: Transaction
  incoming: Transaction
  days_apart: number
}

/** Two sides of a currency exchange between own accounts, on one day. */
export interface ExchangeCandidate {
  outgoing: Transaction
  incoming: Transaction
  /** Pesos per dollar it implies. */
  rate: string
  /** That day's MEP sell rate, to compare. */
  mep: string | null
}

export interface TabularMapping {
  header_row: number
  delimiter: string | null
  date_column: string
  date_format: string
  description_columns: string[]
  amount_column: string | null
  debit_column: string | null
  credit_column: string | null
  decimal_separator: string
  thousands_separator: string
  negate: boolean
}

export interface MappingInput {
  name: string
  account_id: number
  config: TabularMapping
}

export interface Mapping extends MappingInput {
  id: number
}

export interface PreviewRow {
  line_number: number
  date: string
  amount: string
  description: string
  target: string
  account_id: number | null
  reference: string | null
  installment: string | null // "5/8"
  duplicate: boolean
  near_duplicate: boolean
  category_name: string | null
  kind: TransactionKind
}

export interface StatementCheck {
  name: string
  expected: string
  actual: string
  ok: boolean
}

export interface PreviewTarget {
  target: string
  account_id: number | null
  rows: number
}

export interface Preview {
  importer: string
  filename: string
  already_imported: boolean
  new_count: number
  duplicate_count: number
  near_duplicate_count: number
  targets: PreviewTarget[]
  unmapped_targets: string[]
  checks: StatementCheck[]
  metadata: Record<string, string>
  rows: PreviewRow[]
  errors: { line_number: number; message: string }[]
  investments: InvestmentSummary | null
  invoices: InvoiceSummary | null
}

/** What a broker statement adds besides ledger rows: operations and a holdings snapshot. */
export interface InvestmentSummary {
  as_of: string | null
  source: 'tenencias' | 'movimientos' | null
  positions: number
  cash: number
  operations: number
  new_operations: number
  replaces_snapshot: boolean
}

export interface SourceAccount {
  key: string
  account_id: number
}

export interface ImportBatch {
  id: number
  account_id: number | null
  importer: string
  filename: string
  rows_imported: number
  rows_duplicate: number
  rows_skipped: number
}

export interface MonthSummary {
  month: string
  income_ars: string
  income_usd: string
  expense_ars: string
  expense_usd: string
  net_ars: string
  net_usd: string
  missing_rate: number
}

export interface CategoryTotal {
  category: string
  ars: string
  usd: string
  missing_rate: number
}

export interface MarketStatus {
  latest_rate_date: string | null
  latest_rate: string | null
  stale: boolean
}

export interface PositionValue {
  ticker: string
  name: string
  asset_class: string
  quantity: string
  /** `mercado`: the public panel's last price; `resumen`: the holdings statement's. */
  price: { price: string; date: string; origin: 'mercado' | 'resumen' } | null
  value_ars: string | null
  value_usd: string | null
}

export interface CashValue {
  label: string
  currency: Currency
  amount: string
  value_ars: string | null
  value_usd: string | null
}

export interface Portfolio {
  as_of: string
  quantities_as_of: string | null
  cash_as_of: string | null
  total_ars: string
  total_usd: string | null
  missing_price: number
  positions: PositionValue[]
  cash: CashValue[]
  allocation: { asset_class: string; ars: string }[]
}

export interface MonthAmount {
  month: string
  ars: string
  usd: string
  missing_rate: number
}

/** What an ARCA file adds: invoices from Mis Comprobantes, or one invoice's PDF. */
export interface InvoiceSummary {
  invoices: number
  new: number
  changed: string[]
  pdf_for: string | null
  /** No invoice matches the PDF yet: importing it creates the invoice. */
  pdf_creates: boolean
}

export interface MonotributoCategory {
  letter: string
  annual_cap: string
  monthly_services: string
}

export interface MonotributoStatus {
  today: string
  table_valid_from: string
  categories: MonotributoCategory[]
  category: MonotributoCategory | null
  window_start: string
  window_end: string
  income: string
  usage: string | null
  /** The highest warning level reached: "0.8", "0.9" or "1". */
  level: string | null
  margin: string | null
  next: {
    deadline: string
    window_start: string
    window_end: string
    income: string
    /** null: above the highest category. */
    implied: MonotributoCategory | null
  }
  monthly: { month: string; ars: string }[]
  projection: MonotributoProjection
}

/** The next 6 months, each invoicing `amount` (this month first). */
export interface MonotributoProjection {
  amount: string
  currency: Currency
  /** Pesos per unit, from the latest invoice in that currency. */
  rate: string
  /** The owner's own amount; otherwise last month's invoicing. */
  manual: boolean
  last_month: string
  last_month_amount: string
  /** Last month differs from the owner's amount: ask whether to update it. */
  ask: boolean
  monthly_ars: string
  months: { month: string; invoiced: string; rolling: string; usage: string | null; level: string | null }[]
  first_over: string | null
  recategorization_income: string
  implied: MonotributoCategory | null
}

export interface Invoice {
  id: number
  type_code: number
  type_label: string
  number: string
  issued_on: string
  receiver_name: string
  currency: Currency
  total: string
  fx_rate: string
  /** Signed: credit notes subtract. */
  total_ars: string
  has_pdf: boolean
  /** `pdf`: known from its PDF alone, until a Mis Comprobantes export confirms it. */
  source: 'export' | 'pdf'
  payment: InvoicePayment | null
  /** The likely payment, to confirm. */
  suggestion: InvoicePayment | null
}

/** A movement that paid, or may have paid, an invoice. */
export interface InvoicePayment {
  transaction_id: number
  date: string
  amount: string
  currency: Currency
  account_name: string
  description: string
  /** The invoice total, to the cent. */
  exact: boolean
}

export interface AuthStatus {
  /** A password is set on the server. */
  required: boolean
  /** This browser may use the API. */
  authenticated: boolean
}

/** What a rule would do before it's created. */
export interface RulePreview {
  /** Uncategorized movements it would catch. */
  would_categorize: number
  /** Movements already in a category that it also matches. */
  conflicts: number
}

/** Uncategorized movements grouped by merchant, with the rule that would catch them. */
export interface RuleSuggestion extends RulePreview {
  pattern: string
  example: string
  sign: Exclude<AmountSign, 'any'>
  count: number
  first_date: string
  last_date: string
  accounts: string[]
  total_ars: string
  missing_rate: number
}
