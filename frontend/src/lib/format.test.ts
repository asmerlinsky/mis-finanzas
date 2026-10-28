import { describe, expect, it } from 'vitest'

import { queryString } from '../api/client'
import { formatDate, formatMoney, formatMonth, lastMonthsRange, monthsBetween } from './format'

// Intl uses non-breaking spaces between symbol and number.
const plain = (text: string) => text.replace(/\s/g, ' ')

describe('monthsBetween', () => {
  it('lists every month across a year end', () => {
    expect(monthsBetween('2025-11-01', '2026-02-28')).toEqual(['2025-11', '2025-12', '2026-01', '2026-02'])
  })
})

describe('format', () => {
  it('formats ARS and USD with Argentine separators', () => {
    expect(plain(formatMoney('-1234.5', 'ARS'))).toBe('-$ 1.234,50')
    expect(plain(formatMoney('10', 'USD'))).toBe('US$ 10,00')
  })

  it('formats ISO dates and months without timezone shifts', () => {
    expect(formatDate('2026-01-31')).toBe('31/01/2026')
    expect(formatMonth('2026-03')).toBe('mar 26')
  })

  it('computes the last N calendar months', () => {
    expect(lastMonthsRange(3, new Date(2026, 0, 15))).toEqual({ start: '2025-11-01', end: '2026-01-31' })
    expect(lastMonthsRange(1, new Date(2024, 1, 10))).toEqual({ start: '2024-02-01', end: '2024-02-29' })
  })
})

describe('queryString', () => {
  it('skips empty values and false flags', () => {
    expect(queryString({ search: '', uncategorized: false, account_id: undefined })).toBe('')
    expect(queryString({ search: 'cafe', uncategorized: true, offset: 0 })).toBe(
      '?search=cafe&uncategorized=true&offset=0',
    )
  })
})
