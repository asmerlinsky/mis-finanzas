import type { AccountKind, Currency, TransactionKind } from '../api/types'

const FORMATTERS: Record<Currency, Intl.NumberFormat> = {
  ARS: new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' }),
  USD: new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'USD' }),
}

/** Format a decimal string from the API, e.g. "-1234.5" -> "-$ 1.234,50". */
export function formatMoney(value: string | number, currency: Currency): string {
  return FORMATTERS[currency].format(Number(value))
}

/** "2026-01-31" -> "31/01/2026", without timezone shifts. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** "2026-03" -> "mar 26". */
export function formatMonth(month: string): string {
  const [year, number] = month.split('-')
  return `${MONTHS[Number(number) - 1]} ${year.slice(2)}`
}

function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** The last `months` calendar months including the current one, as ISO dates. */
export function lastMonthsRange(months: number, today: Date = new Date()) {
  const first = new Date(today.getFullYear(), today.getMonth() - (months - 1), 1)
  const last = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  return { start: isoDate(first), end: isoDate(last) }
}

export const KIND_LABELS: Record<TransactionKind, string> = {
  income: 'Ingreso',
  expense: 'Gasto',
  transfer: 'Transferencia',
  fx: 'Cambio',
  investment: 'Inversión',
}

export const ACCOUNT_KIND_LABELS: Record<AccountKind, string> = {
  bank: 'Banco',
  card: 'Tarjeta',
  wallet: 'Billetera',
  broker: 'Broker',
}
