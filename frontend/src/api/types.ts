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
