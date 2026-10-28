import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Category, RuleSuggestion } from '../../api/types'
import { Suggestions } from './Suggestions'

const SUGGESTION: RuleSuggestion = {
  pattern: 'PAYU/AR/UBER',
  example: 'Payu/ar/uber',
  sign: 'debit',
  count: 3,
  first_date: '2026-03-02',
  last_date: '2026-03-04',
  accounts: ['Banco pesos'],
  total_ars: '-600.00',
  missing_rate: 0,
  would_categorize: 3,
  conflicts: 1,
}
const CATEGORIES: Category[] = [{ id: 7, name: 'Transporte', kind: null }]

type Call = [string, RequestInit | undefined]

function serve() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST' && url === '/api/categories') {
      return new Response(JSON.stringify({ id: 9, name: 'Movilidad', kind: null }), { status: 201 })
    }
    if (init?.method === 'POST' && url === '/api/rules/apply') {
      return new Response(JSON.stringify({ categorized: 3 }), { status: 200 })
    }
    if (init?.method === 'POST') return new Response('{}', { status: 201 })
    if (url.startsWith('/api/rules/preview')) {
      return new Response(JSON.stringify({ would_categorize: 5, conflicts: 0 }), { status: 200 })
    }
    const body = url === '/api/categories' ? CATEGORIES : [SUGGESTION]
    return new Response(JSON.stringify(body), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Suggestions />
    </QueryClientProvider>,
  )
  return fetchMock
}

function posts(fetchMock: ReturnType<typeof serve>): [string, unknown][] {
  return (fetchMock.mock.calls as Call[])
    .filter(([, init]) => init?.method === 'POST')
    .map(([url, init]) => [url, init?.body ? JSON.parse(String(init.body)) : null])
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Suggestions', () => {
  it('shows a group and what its rule would do', async () => {
    serve()
    const row = (await screen.findByDisplayValue('PAYU/AR/UBER')).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('gasto')
    expect(row).toHaveTextContent('categoriza 3')
    expect(row).not.toHaveTextContent('sin cotización')
    expect(within(row).getByText('también coincide con 1 ya categorizados')).toBeInTheDocument()
  })

  it('creates the rule and applies it', async () => {
    const fetchMock = serve()
    await screen.findByDisplayValue('PAYU/AR/UBER')
    await userEvent.selectOptions(screen.getByLabelText('Categoría para PAYU/AR/UBER'), '7')
    await userEvent.click(screen.getByRole('button', { name: 'Crear regla' }))
    expect(await screen.findByText('Regla creada: 3 movimientos categorizados.')).toBeInTheDocument()
    expect(posts(fetchMock)).toEqual([
      [
        '/api/rules',
        { category_id: 7, pattern: 'PAYU/AR/UBER', match_type: 'contains', account_id: null, sign: 'debit', priority: 100 },
      ],
      ['/api/rules/apply', null],
    ])
  })

  it('creates a new category first, and previews an edited pattern', async () => {
    const fetchMock = serve()
    const input = await screen.findByDisplayValue('PAYU/AR/UBER')
    await userEvent.clear(input)
    await userEvent.type(input, 'UBER')
    await userEvent.click(screen.getByRole('button', { name: 'Probar' }))
    expect(await screen.findByText(/categoriza 5/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Categoría para PAYU/AR/UBER'), 'new')
    await userEvent.type(screen.getByLabelText('Nombre de la categoría'), 'Movilidad')
    await userEvent.click(screen.getByRole('button', { name: 'Crear regla' }))
    await screen.findByText(/Regla creada/)
    const [category, rule] = posts(fetchMock)
    expect(category).toEqual(['/api/categories', { name: 'Movilidad', kind: null }])
    expect(rule).toEqual([
      '/api/rules',
      { category_id: 9, pattern: 'UBER', match_type: 'contains', account_id: null, sign: 'debit', priority: 100 },
    ])
  })
})
