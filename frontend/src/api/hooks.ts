// React Query hooks. Every mutation invalidates all queries: the data set is small and local,
// and a refetch is simpler than tracking which views each change affects.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, jsonBody, queryString } from './client'
import type {
  Account,
  AuthStatus,
  Category,
  ExchangeCandidate,
  CategoryTotal,
  ImportBatch,
  Invoice,
  Mapping,
  MarketStatus,
  MonthAmount,
  MonthSummary,
  MonotributoStatus,
  Portfolio,
  Rule,
  RuleSuggestion,
  SourceAccount,
  TransactionFilters,
  TransactionPage,
  TransferCandidate,
} from './types'

export const useAccounts = () =>
  useQuery({ queryKey: ['accounts'], queryFn: () => api<Account[]>('/accounts') })

export const useCategories = () =>
  useQuery({ queryKey: ['categories'], queryFn: () => api<Category[]>('/categories') })

export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: () => api<Rule[]>('/rules') })

export const useRuleSuggestions = () =>
  useQuery({
    queryKey: ['rule-suggestions'],
    queryFn: () => api<RuleSuggestion[]>('/rules/suggestions'),
  })

export const useMappings = () =>
  useQuery({ queryKey: ['mappings'], queryFn: () => api<Mapping[]>('/mappings') })

export const useSourceAccounts = () =>
  useQuery({ queryKey: ['source-accounts'], queryFn: () => api<SourceAccount[]>('/source-accounts') })

/** `santander/CA/ARS` as a URL path, each segment escaped. */
export const sourceAccountPath = (key: string) =>
  `/source-accounts/${key.split('/').map(encodeURIComponent).join('/')}`

export const useImports = () =>
  useQuery({ queryKey: ['imports'], queryFn: () => api<ImportBatch[]>('/imports') })

export const useTransactions = (filters: TransactionFilters) =>
  useQuery({
    queryKey: ['transactions', filters],
    queryFn: () => api<TransactionPage>(`/transactions${queryString(filters)}`),
  })

export const useTransferCandidates = () =>
  useQuery({
    queryKey: ['transfer-candidates'],
    queryFn: () => api<TransferCandidate[]>('/transfers/candidates'),
  })

export const useExchangeCandidates = () =>
  useQuery({
    queryKey: ['exchange-candidates'],
    queryFn: () => api<ExchangeCandidate[]>('/exchanges/candidates'),
  })

export const useMonthly = (start: string, end: string) =>
  useQuery({
    queryKey: ['monthly', start, end],
    queryFn: () => api<MonthSummary[]>(`/reports/monthly${queryString({ start, end })}`),
  })

export const useCategoryTotals = (start: string, end: string) =>
  useQuery({
    queryKey: ['category-totals', start, end],
    queryFn: () => api<CategoryTotal[]>(`/reports/categories${queryString({ start, end })}`),
  })

export const usePortfolio = () =>
  useQuery({ queryKey: ['portfolio'], queryFn: () => api<Portfolio>('/investments/portfolio') })

export const useDividends = (start: string, end: string) =>
  useQuery({
    queryKey: ['dividends', start, end],
    queryFn: () => api<MonthAmount[]>(`/investments/dividends${queryString({ start, end })}`),
  })

export const useMonotributoStatus = () =>
  useQuery({
    queryKey: ['monotributo-status'],
    queryFn: () => api<MonotributoStatus>('/monotributo/status'),
  })

export const useInvoices = () =>
  useQuery({ queryKey: ['invoices'], queryFn: () => api<Invoice[]>('/monotributo/invoices') })

export const useAuthStatus = () =>
  useQuery({ queryKey: ['auth-status'], queryFn: () => api<AuthStatus>('/auth/status') })

export const useMarketStatus = () =>
  useQuery({ queryKey: ['market-status'], queryFn: () => api<MarketStatus>('/market/status') })

/** A mutation that refetches everything once it succeeds. */
export function useApiMutation<TInput, TResult = unknown>(fn: (input: TInput) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => client.invalidateQueries() })
}

export const send = <T>(method: string, path: string, body?: unknown) =>
  api<T>(path, body === undefined ? { method } : jsonBody(method, body))

export const uploadFile = <T>(path: string, fields: Record<string, string>, file: File) => {
  const form = new FormData()
  for (const [key, value] of Object.entries(fields)) form.set(key, value)
  form.set('file', file)
  return api<T>(path, { method: 'POST', body: form })
}
