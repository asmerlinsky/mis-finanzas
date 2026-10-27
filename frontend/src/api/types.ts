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
  duplicate: boolean
  category_name: string | null
  kind: TransactionKind
}

export interface Preview {
  filename: string
  already_imported: boolean
  new_count: number
  duplicate_count: number
  rows: PreviewRow[]
  errors: { line_number: number; message: string }[]
}

export interface ImportBatch {
  id: number
  account_id: number
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
