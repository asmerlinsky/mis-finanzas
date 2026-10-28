import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Login } from './Login'

function serve(status: number) {
  const fetchMock = vi.fn(async () =>
    status === 204 ? new Response(null, { status }) : new Response('{"detail":"x"}', { status }),
  )
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Login />
    </QueryClientProvider>,
  )
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Login', () => {
  it('posts the password', async () => {
    const fetchMock = serve(204)
    await userEvent.type(screen.getByLabelText('Contraseña'), 'una clave larga')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ password: 'una clave larga' }) }),
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it.each([
    [401, 'Contraseña incorrecta.'],
    [429, 'Demasiados intentos fallidos'],
  ])('explains a refused login (%i)', async (status, message) => {
    serve(status)
    await userEvent.type(screen.getByLabelText('Contraseña'), 'otra clave')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })
})
