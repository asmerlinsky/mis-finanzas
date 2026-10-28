// Expenses per category and month. Clicking a cell lists the movements that make it up.

import { useState } from 'react'

import { useCategoryMonths, useTransactions } from '../../api/hooks'
import type { CategoryMonths, Currency, TransactionFilters } from '../../api/types'
import { Empty, ErrorNote, Money } from '../../components/ui'
import { formatDate, formatMonth, monthsBetween } from '../../lib/format'

const MAX_ITEMS = 500

interface Cell {
  category: string
  categoryId: number | null
  /** null: the whole range (the Total column). */
  month: string | null
  amount: string
}

/** First and last day of "YYYY-MM", as ISO dates. */
function monthRange(month: string): { start: string; end: string } {
  const [year, number] = month.split('-').map(Number)
  const last = new Date(year, number, 0).getDate()
  return { start: `${month}-01`, end: `${month}-${String(last).padStart(2, '0')}` }
}

function cellFilters(cell: Cell, range: { start: string; end: string }): TransactionFilters {
  const dates = cell.month ? monthRange(cell.month) : range
  const category = cell.categoryId === null ? { uncategorized: true } : { category_id: cell.categoryId }
  return { ...category, kind: 'expense', ...dates, limit: MAX_ITEMS }
}

/** The movements a cell sums: same category, kind and dates. */
function CellItems({ cell, range, currency, onClose }: {
  cell: Cell
  range: { start: string; end: string }
  currency: Currency
  onClose: () => void
}) {
  const items = useTransactions(cellFilters(cell, range))
  const page = items.data
  return (
    <div className="card-inset">
      <div className="card-header">
        <h3>
          {cell.category} · {cell.month ? formatMonth(cell.month) : 'todo el período'}
        </h3>
        <button className="link" onClick={onClose}>
          Cerrar
        </button>
      </div>
      <ErrorNote error={items.error} />
      {page && (
        <table>
          <tbody>
            {page.items.map((tx) => (
              <tr key={tx.id}>
                <td>{formatDate(tx.date)}</td>
                <td className="muted">{tx.account_name}</td>
                <td>{tx.description}</td>
                <td className="num">
                  <Money value={tx.amount} currency={tx.currency} />
                </td>
              </tr>
            ))}
            <tr>
              <td colSpan={3}>
                <strong>Total</strong>
                {page.total > page.items.length && (
                  <span className="muted"> ({page.total - page.items.length} más sin mostrar)</span>
                )}
              </td>
              <td className="num">
                <strong>
                  <Money value={cell.amount} currency={currency} />
                </strong>
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}

function CellButton({ amount, currency, selected, onClick }: {
  amount: string | undefined
  currency: Currency
  selected: boolean
  onClick: () => void
}) {
  if (amount === undefined) return <span className="muted">—</span>
  return (
    <button className={`cell${selected ? ' selected' : ''}`} onClick={onClick}>
      <Money value={amount} currency={currency} />
    </button>
  )
}

function sameCell(a: Cell | null, b: Cell): boolean {
  return a !== null && a.category === b.category && a.month === b.month
}

export function CategoryMonthTable({ range, currency }: {
  range: { start: string; end: string }
  currency: Currency
}) {
  const found = useCategoryMonths(range.start, range.end)
  const [open, setOpen] = useState<Cell | null>(null)
  const months = monthsBetween(range.start, range.end)
  const key = currency === 'ARS' ? 'ars' : 'usd'
  const toggle = (cell: Cell) => setOpen(sameCell(open, cell) ? null : cell)
  const rows: CategoryMonths[] = found.data ?? []
  if (found.data && rows.length === 0) return <Empty>No hay gastos en el período.</Empty>
  return (
    <>
      <ErrorNote error={found.error} />
      <div className="table-scroll">
        <table className="category-months">
          <thead>
            <tr>
              <th>Categoría</th>
              {months.map((m) => (
                <th key={m} className="num">
                  {formatMonth(m)}
                </th>
              ))}
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const byMonth = new Map(row.months.map((m) => [m.month, m[key]]))
              const base = { category: row.category, categoryId: row.category_id }
              const total = currency === 'ARS' ? row.total_ars : row.total_usd
              return (
                <tr key={row.category}>
                  <td>{row.category}</td>
                  {months.map((m) => {
                    const cell = { ...base, month: m, amount: byMonth.get(m) ?? '0' }
                    return (
                      <td key={m} className="num">
                        <CellButton amount={byMonth.get(m)} currency={currency}
                          selected={sameCell(open, cell)} onClick={() => toggle(cell)} />
                      </td>
                    )
                  })}
                  <td className="num">
                    <CellButton amount={total} currency={currency}
                      selected={sameCell(open, { ...base, month: null, amount: total })}
                      onClick={() => toggle({ ...base, month: null, amount: total })} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {open && <CellItems cell={open} range={range} currency={currency} onClose={() => setOpen(null)} />}
    </>
  )
}
