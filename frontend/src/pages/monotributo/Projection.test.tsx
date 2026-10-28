import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MonotributoProjection, MonotributoStatus } from '../../api/types'
import { Projection } from './Projection'

const CATEGORY = { letter: 'A', annual_cap: '1000000', monthly_services: '10000' }
const PROJECTION: MonotributoProjection = {
  amount: '3500', currency: 'USD', rate: '1000', manual: true, last_month: '2026-10',
  last_month_amount: '0', ask: false, monthly_ars: '3500000',
  months: [
    { month: '2026-11', invoiced: '3500000', rolling: '900000', usage: '0.9', level: '0.9' },
    { month: '2026-12', invoiced: '3500000', rolling: '1100000', usage: '1.1', level: '1' },
  ],
  first_over: '2026-12', recategorization_income: '1100000', implied: null,
}
const STATUS = {
  category: CATEGORY,
  next: { deadline: '2027-02-05', window_start: '2026-01-01', window_end: '2026-12-31' },
} as MonotributoStatus

function serve(projection: MonotributoProjection) {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Projection status={{ ...STATUS, projection }} />
    </QueryClientProvider>,
  )
  return fetchMock
}

function sent(fetchMock: ReturnType<typeof serve>) {
  return fetchMock.mock.calls.map(([url, init]) => [init?.method, url, JSON.parse(String(init?.body))])
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Projection', () => {
  it('shows the months and when the cap would be passed', () => {
    serve(PROJECTION)
    expect(screen.getByText(/Suponiendo/)).toHaveTextContent('US$ 3.500,00 por mes (tu monto)')
    expect(screen.getByText(/superarías el tope de la categoría A en dic 26/)).toBeInTheDocument()
    expect(screen.getByText('supera el tope')).toBeInTheDocument()
    expect(screen.getByText(/corresponderías a/)).toHaveTextContent('más que la categoría más alta')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('asks to update the amount when last month was different', async () => {
    const fetchMock = serve({ ...PROJECTION, ask: true, last_month_amount: '3200' })
    expect(screen.getByRole('alert')).toHaveTextContent('En oct 26 facturaste US$ 3.200,00')
    await userEvent.click(screen.getByRole('button', { name: /^Usar US\$\s3\.200,00$/ }))
    await userEvent.click(screen.getByRole('button', { name: /^Mantener US\$\s3\.500,00$/ }))
    expect(sent(fetchMock)).toEqual([
      ['PUT', '/api/monotributo/projection', { amount: '3200', currency: 'USD' }],
      ['PUT', '/api/monotributo/projection', { amount: '3500', currency: 'USD' }],
    ])
  })

  it('lets the owner set their own amount', async () => {
    const fetchMock = serve({ ...PROJECTION, manual: false })
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar' }))
    const input = screen.getByLabelText('Monto por mes')
    await userEvent.clear(input)
    await userEvent.type(input, '4000,50')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(sent(fetchMock)).toEqual([
      ['PUT', '/api/monotributo/projection', { amount: '4000.50', currency: 'USD' }],
    ])
  })
})
