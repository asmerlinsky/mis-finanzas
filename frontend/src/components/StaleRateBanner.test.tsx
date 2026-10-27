import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MarketStatus } from '../api/types'
import { StaleRateBanner } from './StaleRateBanner'

function renderWith(status: MarketStatus) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(status), { status: 200 })))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <StaleRateBanner />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('StaleRateBanner', () => {
  it('warns when no rate was ever downloaded', async () => {
    renderWith({ latest_rate_date: null, latest_rate: null, stale: true })
    expect(await screen.findByText(/no hay cotización MEP/)).toBeInTheDocument()
  })

  it('warns when the rate is stale', async () => {
    renderWith({ latest_rate_date: '2026-03-06', latest_rate: '1500.25', stale: true })
    expect(await screen.findByText(/desactualizada: la última es del 06\/03\/2026/)).toBeInTheDocument()
  })

  it('shows the current rate', async () => {
    renderWith({ latest_rate_date: '2026-03-06', latest_rate: '1500.25', stale: false })
    expect(await screen.findByText(/Dólar MEP/)).toHaveTextContent('1.500,25')
  })
})
