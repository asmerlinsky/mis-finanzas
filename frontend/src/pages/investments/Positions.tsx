// Positions grouped by asset class, with each one's weight, price (and how old it is) and the
// gain on the part whose cost is known. Cash goes last. Headers sort within each class.

import { useState } from 'react'

import type { CashValue, Currency, Portfolio, PositionValue } from '../../api/types'
import { Money } from '../../components/ui'
import { formatDate, formatPercent, formatQuantity } from '../../lib/format'

type SortKey = 'ticker' | 'value' | 'weight' | 'gain'

const ORIGIN_LABELS = { mercado: 'mercado', resumen: 'resumen' } as const
const OLD_PRICE_DAYS = 3
const DAY_MS = 86_400_000

function valueIn(item: { value_ars: string | null; value_usd: string | null }, currency: Currency) {
  const value = currency === 'ARS' ? item.value_ars : item.value_usd
  return value === null ? null : Number(value)
}

function gainIn(p: PositionValue, currency: Currency) {
  const gain = currency === 'ARS' ? p.gain_ars : p.gain_usd
  const cost = currency === 'ARS' ? p.cost_ars : p.cost_usd
  return gain === null || cost === null ? null : { gain: Number(gain), cost: Number(cost) }
}

function sortValue(p: PositionValue, key: SortKey, currency: Currency): number | string {
  if (key === 'ticker') return p.ticker
  if (key === 'gain') return gainIn(p, currency)?.gain ?? -Infinity
  return valueIn(p, currency) ?? -Infinity // weight sorts like value within a class
}

function sorted(positions: PositionValue[], key: SortKey, currency: Currency): PositionValue[] {
  return [...positions].sort((a, b) => {
    const [x, y] = [sortValue(a, key, currency), sortValue(b, key, currency)]
    if (typeof x === 'string' && typeof y === 'string') return x.localeCompare(y)
    return Number(y) - Number(x)
  })
}

/** The newest price shown; a price more than `OLD_PRICE_DAYS` older is flagged. */
function newestPriceDate(positions: PositionValue[]): number | null {
  const dates = positions.flatMap((p) => (p.price ? [Date.parse(p.price.date)] : []))
  return dates.length ? Math.max(...dates) : null
}

function PriceCell({ position, newest }: { position: PositionValue; newest: number | null }) {
  if (!position.price) return <span className="muted">sin precio</span>
  const { price, date, origin } = position.price
  const old = newest !== null && newest - Date.parse(date) > OLD_PRICE_DAYS * DAY_MS
  return (
    <>
      <Money value={price} currency="ARS" />
      <span className="muted small">
        {' '}
        {ORIGIN_LABELS[origin]} {formatDate(date)}
      </span>
      {old && <span className="tag warn">precio viejo</span>}
    </>
  )
}

function GainCell({ position, currency }: { position: PositionValue; currency: Currency }) {
  const found = gainIn(position, currency)
  if (found === null) return <span className="muted">sin costo conocido</span>
  const coverage = Number(position.coverage ?? 0)
  return (
    <>
      <Money value={found.gain} currency={currency} />
      {found.cost > 0 && <span className="muted small"> {formatPercent(found.gain / found.cost)}</span>}
      {coverage < 1 && <div className="muted small">parcial ({formatPercent(coverage)})</div>}
    </>
  )
}

function Amount({ value, currency }: { value: number | null; currency: Currency }) {
  return value === null ? <span className="muted">—</span> : <Money value={value} currency={currency} />
}

function SortHeader({ label, sortKey, current, onSort, numeric }: {
  label: string
  sortKey: SortKey
  current: SortKey
  onSort: (key: SortKey) => void
  numeric?: boolean
}) {
  return (
    <th className={numeric ? 'num' : undefined}>
      <button className="link" onClick={() => onSort(sortKey)} aria-pressed={current === sortKey}>
        {label}
        {current === sortKey ? ' ▾' : ''}
      </button>
    </th>
  )
}

function ClassRows({ name, positions, total, currency, newest }: {
  name: string
  positions: PositionValue[]
  total: number
  currency: Currency
  newest: number | null
}) {
  const value = positions.reduce((sum, p) => sum + (valueIn(p, currency) ?? 0), 0)
  const gains = positions.flatMap((p) => gainIn(p, currency)?.gain ?? [])
  const gain = gains.length ? gains.reduce((sum, g) => sum + g, 0) : null
  return (
    <>
      {positions.map((p) => {
        const own = valueIn(p, currency)
        return (
          <tr key={p.ticker}>
            <td><code>{p.ticker}</code></td>
            <td>{p.name}</td>
            <td className="num">{formatQuantity(p.quantity)}</td>
            <td className="num"><PriceCell position={p} newest={newest} /></td>
            <td className="num"><Amount value={own} currency={currency} /></td>
            <td className="num">{own !== null && total > 0 ? formatPercent(own / total) : '—'}</td>
            <td className="num"><GainCell position={p} currency={currency} /></td>
          </tr>
        )
      })}
      <tr className="subtotal">
        <td colSpan={4}>Total {name}</td>
        <td className="num"><Money value={value} currency={currency} /></td>
        <td className="num">{total > 0 ? formatPercent(value / total) : '—'}</td>
        <td className="num"><Amount value={gain} currency={currency} /></td>
      </tr>
    </>
  )
}

function CashRows({ cash, total, currency }: { cash: CashValue[]; total: number; currency: Currency }) {
  if (cash.length === 0) return null
  const value = cash.reduce((sum, c) => sum + (valueIn(c, currency) ?? 0), 0)
  return (
    <>
      {cash.map((c) => (
        <tr key={c.label}>
          <td colSpan={2}>{c.label}</td>
          <td className="num"><Money value={c.amount} currency={c.currency} /></td>
          <td />
          <td className="num"><Amount value={valueIn(c, currency)} currency={currency} /></td>
          <td className="num">{total > 0 ? formatPercent((valueIn(c, currency) ?? 0) / total) : '—'}</td>
          <td />
        </tr>
      ))}
      <tr className="subtotal">
        <td colSpan={4}>Total Monedas</td>
        <td className="num"><Money value={value} currency={currency} /></td>
        <td className="num">{total > 0 ? formatPercent(value / total) : '—'}</td>
        <td />
      </tr>
    </>
  )
}

function byClass(positions: PositionValue[]): [string, PositionValue[]][] {
  const groups = new Map<string, PositionValue[]>()
  for (const p of positions) groups.set(p.asset_class, [...(groups.get(p.asset_class) ?? []), p])
  return [...groups.entries()]
}

export function Positions({ portfolio, currency }: { portfolio: Portfolio; currency: Currency }) {
  const [sortKey, setSortKey] = useState<SortKey>('value')
  const total = Number((currency === 'ARS' ? portfolio.total_ars : portfolio.total_usd) ?? 0)
  const newest = newestPriceDate(portfolio.positions)
  const header = { current: sortKey, onSort: setSortKey }
  return (
    <table className="positions">
      <thead>
        <tr>
          <SortHeader label="Especie" sortKey="ticker" {...header} />
          <th>Descripción</th>
          <th className="num">Cantidad</th>
          <th className="num">Precio</th>
          <SortHeader label="Valor" sortKey="value" numeric {...header} />
          <SortHeader label="Peso" sortKey="weight" numeric {...header} />
          <SortHeader label="Ganancia" sortKey="gain" numeric {...header} />
        </tr>
      </thead>
      <tbody>
        {byClass(portfolio.positions).map(([name, positions]) => (
          <ClassRows key={name} name={name} positions={sorted(positions, sortKey, currency)}
            total={total} currency={currency} newest={newest} />
        ))}
        <CashRows cash={portfolio.cash} total={total} currency={currency} />
      </tbody>
    </table>
  )
}
