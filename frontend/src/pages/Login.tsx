// The login screen, shown when the server has a password set and this browser has no session.

import { useState } from 'react'

import { ApiError } from '../api/client'
import { send, useApiMutation } from '../api/hooks'
import { Section } from '../components/ui'

function loginError(error: unknown): string | null {
  if (!error) return null
  if (error instanceof ApiError && error.status === 401) return 'Contraseña incorrecta.'
  if (error instanceof ApiError && error.status === 429) {
    return 'Demasiados intentos fallidos. Probá de nuevo en unos minutos.'
  }
  return error instanceof Error ? error.message : String(error)
}

export function Login() {
  const [password, setPassword] = useState('')
  const login = useApiMutation((value: string) => send('POST', '/auth/login', { password: value }))
  const message = loginError(login.error)
  return (
    <Section title="Ingresar">
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault()
          login.mutate(password)
        }}
      >
        <label>
          Contraseña
          <input
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" disabled={!password || login.isPending}>
          Ingresar
        </button>
      </form>
      {message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}
    </Section>
  )
}
