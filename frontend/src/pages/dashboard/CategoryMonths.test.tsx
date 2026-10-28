import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CategoryMonths } from '../../api/types'
import { CategoryMonthTable } from './CategoryMonths'

const ROWS: CategoryMonths[] = [
  {
    category: 'Comida', category_id: 3,
    months: [{ month: '2026-01', ars: '150.00', usd: '0.15' }, { month: '2026-02', ars: '280.00', usd: '0.28' }],
    total_ars: '430.00', total_usd: '0.43', missing_rate: 0,
  },
  {
    category: 'Sin categoría', category_id: null,
    months: [{ month: '2026-02', ars: '7.00', usd: '0.01' }],
    total_ars: '7.00', total_usd: '0.01', missing_rate: 0,
  },
]
const ITEMS = {
  total: 2,
  items: [
    { id: 1, date: '2026-02-03', account_name: 'Banco', description: 'Super Ejemplo', amount: '-300.00', currency: 'ARS' },
    { id: 2, date: '2026-02-04', account_name: 'Banco', description: 'Devolución', amount: '20.00', currency: 'ARS' },
  ],
}

function serve() {
  const fetchMock = vi.fn(async (url: string) => {
    const body = url.startsWith('/api/reports/categories/monthly') ? ROWS : ITEMS
    return new Response(JSON.stringify(body), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <CategoryMonthTable range={{ start: '2026-01-01', end: '2026-02-28' }} currency="ARS" />
    </QueryClientProvider>,
  )
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CategoryMonthTable', () => {
  it('shows each category per month, with a dash for empty months', async () => {
    serve()
    const row = (await screen.findByText('Sin categoría')).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('—')
    expect(screen.getByRole('columnheader', { name: 'ene 26' })).toBeInTheDocument()
  })

  it('lists the movements of a cell, asking for exactly that cell', async () => {
    const fetchMock = serve()
    await userEvent.click(await screen.findByRole('button', { name: /280,00/ }))
    expect(await screen.findByText('Super Ejemplo')).toBeInTheDocument()
    expect(screen.getByText('Comida · feb 26')).toBeInTheDocument()
    const asked = fetchMock.mock.calls.map(([url]) => url).find((url) => url.startsWith('/api/transactions'))
    expect(asked).toBe('/api/transactions?category_id=3&kind=expense&start=2026-02-01&end=2026-02-28&limit=500')
    await userEvent.click(screen.getByRole('button', { name: /280,00/ }))
    expect(screen.queryByText('Super Ejemplo')).toBeNull()
  })

  it('asks for uncategorized movements over the whole range from a Total cell', async () => {
    const fetchMock = serve()
    const row = (await screen.findByText('Sin categoría')).closest('tr') as HTMLElement
    const buttons = row.querySelectorAll('button')
    await userEvent.click(buttons[buttons.length - 1])
    await screen.findByText('Sin categoría · todo el período')
    const asked = fetchMock.mock.calls.map(([url]) => url).find((url) => url.startsWith('/api/transactions'))
    expect(asked).toBe('/api/transactions?uncategorized=true&kind=expense&start=2026-01-01&end=2026-02-28&limit=500')
  })
})
