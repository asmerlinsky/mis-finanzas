import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PreviewRow } from '../api/types'
import { preview } from '../test-fixtures'
import { Uploader } from './Import'

const ROW: PreviewRow = {
  line_number: 1, date: '2026-09-04', amount: '-100.00', description: 'Movimiento',
  target: 'santander/CA/ARS', account_id: 1, reference: null, installment: null,
  duplicate: false, near_duplicate: false, category_name: null, kind: 'expense',
}
const BATCH = {
  id: 1, account_id: 1, importer: 'santander_account_pdf', filename: 'x.pdf',
  rows_imported: 1, rows_duplicate: 0, rows_skipped: 0, created_at: '2026-10-28T10:00:00',
}

/** The name of the file a request uploaded. */
function fileName(init: RequestInit | undefined): string {
  const form = init?.body
  if (!(form instanceof FormData)) throw new Error('not an upload')
  return (form.get('file') as File).name
}

function serve() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/imports/preview') {
      const name = fileName(init)
      return new Response(JSON.stringify(preview({ filename: name, rows: [ROW] })), { status: 200 })
    }
    if (url === '/api/imports') return new Response(JSON.stringify(BATCH), { status: 201 })
    return new Response('[]', { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Uploader mappingId={null} />
    </QueryClientProvider>,
  )
  return fetchMock
}

const pdf = (name: string) => new File(['%PDF'], name, { type: 'application/pdf' })

function uploaded(fetchMock: ReturnType<typeof serve>, url: string): string[] {
  return fetchMock.mock.calls
    .filter(([called]) => called === url)
    .map(([, init]) => fileName(init))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Uploader', () => {
  it('reviews several files one by one', async () => {
    const fetchMock = serve()
    await userEvent.upload(screen.getByLabelText('Archivos a importar'), [pdf('julio.pdf'), pdf('agosto.pdf')])
    expect(await screen.findByText('(1 de 2)')).toBeInTheDocument()
    expect(screen.getByText('julio.pdf', { selector: '.queue-name' }).closest('li')).toHaveTextContent('revisando')
    await userEvent.click(screen.getByRole('button', { name: 'Importar 1 movimientos' }))
    expect(await screen.findByText('(2 de 2)')).toBeInTheDocument()
    expect(screen.getByText('julio.pdf', { selector: '.queue-name' }).closest('li')).toHaveTextContent(
      'importado Importadas 1 filas',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Saltear este archivo' }))
    expect(await screen.findByText('Listo: 1 importados, 1 salteados.')).toBeInTheDocument()
    // The second file was previewed only once the first was imported; only the first was committed.
    expect(uploaded(fetchMock, '/api/imports/preview')).toEqual(['julio.pdf', 'agosto.pdf'])
    expect(uploaded(fetchMock, '/api/imports')).toEqual(['julio.pdf'])
  })

  it('imports a single file as before, without a queue', async () => {
    serve()
    await userEvent.upload(screen.getByLabelText('Archivos a importar'), pdf('julio.pdf'))
    await userEvent.click(await screen.findByRole('button', { name: 'Importar 1 movimientos' }))
    expect(await screen.findByText(/Importadas 1 filas/)).toBeInTheDocument()
    expect(screen.queryByRole('list')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Saltear este archivo' })).toBeNull()
  })
})
