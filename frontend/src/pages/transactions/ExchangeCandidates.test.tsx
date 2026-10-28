import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ExchangeCandidate, Transaction } from '../../api/types'
import { ExchangeCandidates } from './ExchangeCandidates'

function tx(id: number, account: string, currency: 'ARS' | 'USD', amount: string): Transaction {
  return {
    id, account_id: id, account_name: account, currency, date: '2026-05-08', amount,
    description: 'Liquidacion titulos', kind: 'fx', category_id: 5, category_name: 'Cambio de moneda',
    transfer_pair_id: null,
  } as Transaction
}

const CANDIDATE: ExchangeCandidate = {
  outgoing: tx(1, 'CA dólares', 'USD', '-1000.00'),
  incoming: tx(2, 'CA pesos', 'ARS', '1450000.00'),
  rate: '1450.00',
  mep: '1460.00',
}

function serve() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return new Response(JSON.stringify({ linked: 1 }), { status: 200 })
    const body = url.includes('/exchanges/candidates') ? [CANDIDATE] : []
    return new Response(JSON.stringify(body), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ExchangeCandidates />
    </QueryClientProvider>,
  )
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ExchangeCandidates', () => {
  it('shows each exchange with its rate and the MEP, and links one or all', async () => {
    const fetchMock = serve()
    const row = (await screen.findByText(/CA dólares → CA pesos/)).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('1.450,00 por dólar')
    expect(row).toHaveTextContent('MEP $ 1.460,00')
    await userEvent.click(screen.getByRole('button', { name: 'Vincular' }))
    await userEvent.click(screen.getByRole('button', { name: 'Vincular todos' }))
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts.map(([url, init]) => [url, init?.body ? JSON.parse(String(init.body)) : null])).toEqual([
      ['/api/exchanges', { outgoing_id: 1, incoming_id: 2 }],
      ['/api/exchanges/all', null],
    ])
  })
})
