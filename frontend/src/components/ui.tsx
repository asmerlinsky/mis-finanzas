// Small shared building blocks.

import type { ReactNode } from 'react'

import type { Currency } from '../api/types'
import { formatMoney } from '../lib/format'

export function Money({ value, currency }: { value: string | number; currency: Currency }) {
  const negative = Number(value) < 0
  return <span className={negative ? 'money negative' : 'money'}>{formatMoney(value, currency)}</span>
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return (
    <p className="error" role="alert">
      {message}
    </p>
  )
}

export function Section({ title, actions, children }: {
  title: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="card">
      <header className="card-header">
        <h2>{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted">{children}</p>
}
