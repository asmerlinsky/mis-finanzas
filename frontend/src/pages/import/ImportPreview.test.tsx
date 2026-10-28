import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Account, Preview, PreviewRow } from '../../api/types'
import { preview } from '../../test-fixtures'
import { ImportPreview } from './ImportPreview'

const ACCOUNTS: Account[] = [
  { id: 1, name: 'CA pesos', institution: 'Banco', kind: 'bank', currency: 'ARS' },
  { id: 2, name: 'CA dólares', institution: 'Banco', kind: 'bank', currency: 'USD' },
]

function row(line: number, overrides: Partial<PreviewRow> = {}): PreviewRow {
  return {
    line_number: line, date: '2026-09-04', amount: '-100.00', description: `Movimiento ${line}`,
    target: 'santander/CA/ARS', account_id: 1, reference: null, installment: null,
    duplicate: false, near_duplicate: false, category_name: null, kind: 'expense', ...overrides,
  }
}

function setup(data: Preview) {
  const handlers = { onMap: vi.fn(), onCreate: vi.fn(), onCommit: vi.fn() }
  render(<ImportPreview preview={data} accounts={ACCOUNTS} busy={false} {...handlers} />)
  return handlers
}

describe('ImportPreview', () => {
  it('blocks the import when a statement check fails', () => {
    setup(preview({
      rows: [row(1)],
      checks: [{ name: 'saldo total en pesos', expected: '10.00', actual: '9.00', ok: false }],
    }))
    expect(screen.getByText(/el resumen dice 10.00, se leyó 9.00/)).toBeInTheDocument()
    expect(screen.getByText(/totales del resumen no coinciden/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Importar 1 movimientos/ })).toBeDisabled()
  })

  it('maps an unmapped target to an account of its currency, or creates one', async () => {
    const handlers = setup(preview({
      targets: [{ target: 'santander/CA/USD', account_id: null, rows: 1 }],
      unmapped_targets: ['santander/CA/USD'],
      rows: [row(1, { target: 'santander/CA/USD', account_id: null })],
    }))
    const select = screen.getByLabelText('Cuenta para santander/CA/USD')
    expect([...select.querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      'Elegí una cuenta…', 'CA dólares',
    ])
    expect(screen.getByRole('button', { name: /Importar/ })).toBeDisabled()
    await userEvent.selectOptions(select, '2')
    expect(handlers.onMap).toHaveBeenCalledWith('santander/CA/USD', 2)
    await userEvent.click(screen.getByRole('button', { name: 'Crear «Santander CA dólares»' }))
    expect(handlers.onCreate).toHaveBeenCalledWith('santander/CA/USD')
  })

  it('lets a near-duplicate be left out', async () => {
    const handlers = setup(preview({
      new_count: 2,
      near_duplicate_count: 1,
      rows: [row(1), row(2, { near_duplicate: true })],
    }))
    expect(screen.getByText('posible duplicado')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Importar línea 2'))
    await userEvent.click(screen.getByRole('button', { name: 'Importar 1 movimientos' }))
    expect(handlers.onCommit).toHaveBeenCalledWith({ skipLines: [2], skipInvalid: false })
  })

  it('shows already imported rows without a checkbox', () => {
    setup(preview({ new_count: 0, duplicate_count: 1, rows: [row(1, { duplicate: true })] }))
    expect(screen.getByText('ya importado')).toBeInTheDocument()
    expect(screen.queryByLabelText('Importar línea 1')).toBeNull()
    expect(screen.getByText('No hay movimientos nuevos para importar.')).toBeInTheDocument()
  })
})
