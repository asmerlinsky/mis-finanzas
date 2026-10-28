import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Transaction, TransferCandidate } from '../../api/types'
import { TransferCandidates } from '../Transactions'

function tx(id: number, account: string, amount: string): Transaction {
  return {
    id, account_id: id, account_name: account, currency: 'ARS', date: '2026-09-04', amount,
    description: 'Pago de tarjeta', kind: 'expense', category_id: null, category_name: null,
    transfer_pair_id: null,
  } as Transaction
}

const PAIRS: TransferCandidate[] = [
  { outgoing: tx(1, 'CA pesos', '-1000.00'), incoming: tx(2, 'Visa pesos', '1000.00'), days_apart: 0 },
  { outgoing: tx(3, 'CA pesos', '-500.00'), incoming: tx(4, 'Broker', '500.00'), days_apart: 1 },
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TransferCandidates', () => {
  it('confirms every suggestion at once', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({ linked: 2 }), { status: 200 })
      return new Response(JSON.stringify(url.includes('/transfers/candidates') ? PAIRS : []), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TransferCandidates />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Posibles transferencias entre tus cuentas (2)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar todas' }))
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST').map(([url]) => url)
    expect(posts).toEqual(['/api/transfers/all'])
  })
})
