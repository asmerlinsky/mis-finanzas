import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Invoice, MonotributoStatus } from '../api/types'
import { Monotributo } from './Monotributo'

const CATEGORIES = [
  { letter: 'A', annual_cap: '1000000', monthly_services: '10000' },
  { letter: 'B', annual_cap: '2000000', monthly_services: '20000' },
]

const STATUS: MonotributoStatus = {
  today: '2026-10-28',
  table_valid_from: '2026-08-01',
  categories: CATEGORIES,
  category: CATEGORIES[1],
  window_start: '2025-10-29',
  window_end: '2026-10-28',
  income: '1850000',
  usage: '0.925',
  level: '0.9',
  margin: '150000',
  next: {
    deadline: '2027-02-05',
    window_start: '2026-01-01',
    window_end: '2026-12-31',
    income: '900000',
    implied: CATEGORIES[0],
  },
  monthly: [{ month: '2026-03', ars: '900000' }],
}

const INVOICES: Invoice[] = [
  {
    id: 1, type_code: 19, type_label: 'Factura E', number: '00001-00000007',
    issued_on: '2026-03-10', receiver_name: 'Cliente Ejemplo SRL', currency: 'USD',
    total: '900', fx_rate: '1000', total_ars: '900000', has_pdf: true,
  },
]

function serve(status: MonotributoStatus, invoices: Invoice[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.includes('/monotributo/invoices') ? invoices : status
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Monotributo />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Monotributo', () => {
  it('warns near the cap and shows the next recategorization', async () => {
    serve(STATUS, INVOICES)
    expect(await screen.findByRole('alert')).toHaveTextContent('el 90 % del tope')
    expect(screen.getByText(/Margen \(usaste/)).toHaveTextContent('92,5')
    expect(screen.getByText(/Próxima recategorización/)).toHaveTextContent(
      'hasta el 05/02/2027',
    )
    expect(screen.getByText(/Próxima recategorización/)).toHaveTextContent('categoría A')
    expect(screen.getByRole('link', { name: 'ver' })).toHaveAttribute(
      'href',
      '/api/monotributo/invoices/1/pdf',
    )
  })

  it('says when the year would exceed the highest category', async () => {
    serve({ ...STATUS, level: null, next: { ...STATUS.next, implied: null } }, [])
    expect(await screen.findByText(/quedarías fuera del monotributo/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText(/Importá el CSV/)).toBeInTheDocument()
  })
})
