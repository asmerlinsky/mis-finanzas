import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Invoice, InvoicePayment } from '../../api/types'
import { InvoiceTable } from './Invoices'

const PAYMENT: InvoicePayment = {
  transaction_id: 41, date: '2026-03-20', amount: '3000.00', currency: 'USD',
  account_name: 'CA dólares', description: 'Cobro exportacion', exact: true,
}
const INVOICE: Invoice = {
  id: 1, type_code: 19, type_label: 'Factura E', number: '00001-00000007', issued_on: '2026-03-10',
  receiver_name: 'Cliente Ejemplo SRL', currency: 'USD', total: '3000.00', fx_rate: '1000',
  total_ars: '3000000.00', has_pdf: false, source: 'export', payment: null, suggestion: null,
}

function serve(invoices: Invoice[], candidates: InvoicePayment[] = []) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/candidates')) return new Response(JSON.stringify(candidates), { status: 200 })
    if (init?.method) return new Response(null, { status: 204 })
    return new Response('[]', { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <InvoiceTable invoices={invoices} />
    </QueryClientProvider>,
  )
  return fetchMock
}

function writes(fetchMock: ReturnType<typeof serve>) {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method)
    .map(([url, init]) => [init?.method, url, init?.body ? JSON.parse(String(init.body)) : null])
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InvoiceTable payments', () => {
  it('confirms a suggested payment', async () => {
    const fetchMock = serve([{ ...INVOICE, suggestion: PAYMENT }])
    expect(screen.getByText(/¿20\/03\/2026 · CA dólares\?/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(writes(fetchMock)).toEqual([
      ['PUT', '/api/monotributo/invoices/1/payment', { transaction_id: 41 }],
    ])
  })

  it('lets the owner choose the movement by hand', async () => {
    const other = { ...PAYMENT, transaction_id: 42, amount: '2975.00', exact: false }
    const fetchMock = serve([INVOICE], [PAYMENT, other])
    await userEvent.click(screen.getByRole('button', { name: 'Elegir movimiento' }))
    const select = await screen.findByLabelText('Movimiento para 00001-00000007')
    expect(screen.getByRole('option', { name: /\(otro monto\)/ })).toBeInTheDocument()
    await userEvent.selectOptions(select, '42')
    await userEvent.click(screen.getByRole('button', { name: 'Vincular' }))
    expect(writes(fetchMock)).toEqual([
      ['PUT', '/api/monotributo/invoices/1/payment', { transaction_id: 42 }],
    ])
  })

  it('shows a linked payment, which can be unlinked, and no payment for a credit note', async () => {
    const creditNote = { ...INVOICE, id: 2, type_code: 21, type_label: 'Nota de Crédito E', number: '00001-00000002' }
    const fetchMock = serve([{ ...INVOICE, payment: PAYMENT }, creditNote])
    expect(screen.getByText(/20\/03\/2026 · CA dólares/)).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(1)  // only "desvincular"
    await userEvent.click(screen.getByRole('button', { name: 'desvincular' }))
    expect(writes(fetchMock)).toEqual([['DELETE', '/api/monotributo/invoices/1/payment', null]])
  })
})
