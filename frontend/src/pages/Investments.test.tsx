import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MonthAmount, Portfolio } from '../api/types'
import { Investments } from './Investments'

const PORTFOLIO: Portfolio = {
  as_of: '2026-10-28',
  quantities_as_of: '2026-10-20',
  cash_as_of: '2026-10-20',
  total_ars: '121500.00',
  total_usd: '121.50',
  missing_price: 1,
  positions: [
    {
      ticker: 'DOS', name: 'ACCION DOS S.A.', asset_class: 'Acciones', quantity: '110',
      price: { price: '1100', date: '2026-10-28', origin: 'mercado' },
      value_ars: '121000.00', value_usd: '121.00',
    },
    {
      ticker: 'FCI1', name: 'FONDO UNO', asset_class: 'Fondos', quantity: '10',
      price: null, value_ars: null, value_usd: null,
    },
  ],
  cash: [{ label: 'Pesos', currency: 'ARS', amount: '500', value_ars: '500', value_usd: '0.50' }],
  allocation: [
    { asset_class: 'Acciones', ars: '121000.00' },
    { asset_class: 'Monedas', ars: '500' },
  ],
}

function serve(portfolio: Portfolio, dividends: MonthAmount[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.includes('/investments/dividends') ? dividends : portfolio
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Investments />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Investments', () => {
  it('shows the total, positions with their price source, and cash', async () => {
    serve(PORTFOLIO, [])
    const total = (await screen.findByText('Valor total')).parentElement as HTMLElement
    expect(total).toHaveTextContent('121.500,00')
    expect(screen.getByText('1 posiciones sin precio no suman en el total.')).toBeInTheDocument()
    const row = screen.getByText('ACCION DOS S.A.').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('mercado 28/10/2026')
    expect(within(screen.getByText('FONDO UNO').closest('tr') as HTMLElement).getByText('sin precio'))
      .toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'USD MEP' }))
    expect(total).toHaveTextContent('121,50')
    expect(screen.getByText('No hay dividendos en el período.')).toBeInTheDocument()
  })

  it('asks for a statement when nothing is held', async () => {
    serve({ ...PORTFOLIO, positions: [], cash: [], allocation: [], total_ars: '0' }, [])
    expect(await screen.findByText(/Importá un resumen de Balanz/)).toBeInTheDocument()
  })

  it('totals dividends net of fees', async () => {
    serve(PORTFOLIO, [
      { month: '2026-03', ars: '2498.50', usd: '2.50', missing_rate: 0 },
      { month: '2026-06', ars: '1000.00', usd: '1.00', missing_rate: 0 },
    ])
    expect(await screen.findByText(/Total del período/)).toHaveTextContent('3.498,50')
  })
})
