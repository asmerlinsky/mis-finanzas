import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HistoryPoint, InstrumentDividends, MonthAmount, Portfolio } from '../api/types'
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
      coverage: '1', cost_ars: '100000.00', cost_usd: '100.00', gain_ars: '21000.00', gain_usd: '21.00',
    },
    {
      ticker: 'FCI1', name: 'FONDO UNO', asset_class: 'Fondos', quantity: '10',
      price: null, value_ars: null, value_usd: null,
      coverage: null, cost_ars: null, cost_usd: null, gain_ars: null, gain_usd: null,
    },
  ],
  cash: [{ label: 'Pesos', currency: 'ARS', amount: '500', value_ars: '500', value_usd: '0.50' }],
  allocation: [
    { asset_class: 'Acciones', ars: '121000.00' },
    { asset_class: 'Monedas', ars: '500' },
  ],
  cost_ars: '100000.00', gain_ars: '21000.00', cost_usd: '100.00', gain_usd: '21.00',
}

const HISTORY: HistoryPoint[] = [
  { date: '2026-10-20', ars: '110000.00', usd: '110.00', source: 'resumen' },
  { date: '2026-10-28', ars: '121500.00', usd: '121.50', source: 'mercado' },
]
const BY_INSTRUMENT: InstrumentDividends[] = [
  { ticker: 'EJM', name: 'CEDEAR EJEMPLO', ars: '2498.50', usd: '2.50', payments: 1, missing_rate: 0 },
]

function answer(url: string, portfolio: Portfolio, dividends: MonthAmount[]): unknown {
  if (url.startsWith('/api/investments/history')) return HISTORY
  if (url.startsWith('/api/investments/dividends/by-instrument')) return BY_INSTRUMENT
  if (url.startsWith('/api/investments/dividends')) return dividends
  return portfolio
}

function serve(portfolio: Portfolio, dividends: MonthAmount[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => new Response(JSON.stringify(answer(url, portfolio, dividends)), { status: 200 })),
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

  it('totals dividends net of fees, also per instrument', async () => {
    serve(PORTFOLIO, [
      { month: '2026-03', ars: '2498.50', usd: '2.50', missing_rate: 0 },
      { month: '2026-06', ars: '1000.00', usd: '1.00', missing_rate: 0 },
    ])
    expect(await screen.findByText(/Total del período/)).toHaveTextContent('3.498,50')
    const row = (await screen.findByText('CEDEAR EJEMPLO')).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('EJM')
    expect(row).toHaveTextContent('2.498,50')
  })

  it('shows the gain over the known cost', async () => {
    serve(PORTFOLIO, [])
    const tile = (await screen.findByText('Ganancia (sobre el costo conocido)')).parentElement as HTMLElement
    expect(tile).toHaveTextContent('21.000,00')
    expect(tile).toHaveTextContent('21%')
    expect(screen.getByText('Valor en el tiempo')).toBeInTheDocument()
  })
})
