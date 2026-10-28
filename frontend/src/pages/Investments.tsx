// What the portfolio is worth today, where it sits, and the dividends it paid.

import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useDividends, usePortfolio } from '../api/hooks'
import type { Currency, MonthAmount, Portfolio } from '../api/types'
import { Empty, ErrorNote, Money, Section } from '../components/ui'
import { formatDate, formatMoney, formatMonth, formatPercent, lastMonthsRange, monthsBetween } from '../lib/format'
import { DividendsByInstrument } from './investments/DividendsByInstrument'
import { History } from './investments/History'
import { Positions } from './investments/Positions'

const RANGES = [12, 24, 36]

function CurrencyToggle({ value, onChange }: { value: Currency; onChange: (c: Currency) => void }) {
  return (
    <div className="toggle" role="group" aria-label="Moneda">
      {(['ARS', 'USD'] as const).map((c) => (
        <button key={c} className={c === value ? 'active' : ''} onClick={() => onChange(c)}>
          {c === 'USD' ? 'USD MEP' : c}
        </button>
      ))}
    </div>
  )
}

function GainTile({ portfolio, currency }: { portfolio: Portfolio; currency: Currency }) {
  const gain = Number(currency === 'ARS' ? portfolio.gain_ars : portfolio.gain_usd)
  const cost = Number(currency === 'ARS' ? portfolio.cost_ars : portfolio.cost_usd)
  if (cost <= 0) return <>—</>
  return (
    <>
      <Money value={gain} currency={currency} /> <span className="muted small">{formatPercent(gain / cost)}</span>
    </>
  )
}

function Totals({ portfolio, currency }: { portfolio: Portfolio; currency: Currency }) {
  const total = currency === 'ARS' ? portfolio.total_ars : portfolio.total_usd
  const tiles = [
    {
      label: 'Valor total',
      value: total === null ? 'sin cotización MEP' : <Money value={total} currency={currency} />,
    },
    {
      label: 'Ganancia (sobre el costo conocido)',
      value: <GainTile portfolio={portfolio} currency={currency} />,
    },
    {
      label: 'Cantidades al',
      value: portfolio.quantities_as_of ? formatDate(portfolio.quantities_as_of) : '—',
    },
    { label: 'Monedas al', value: portfolio.cash_as_of ? formatDate(portfolio.cash_as_of) : '—' },
  ]
  return (
    <div className="tiles">
      {tiles.map((tile) => (
        <div className="tile" key={tile.label}>
          <span className="muted">{tile.label}</span>
          <strong>{tile.value}</strong>
        </div>
      ))}
    </div>
  )
}

function Allocation({ portfolio }: { portfolio: Portfolio }) {
  const total = Number(portfolio.total_ars)
  if (total <= 0) return null
  const data = portfolio.allocation.map((a) => ({
    name: a.asset_class,
    share: Number(a.ars) / total,
    ars: Number(a.ars),
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={40 + 36 * data.length}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
          <XAxis
            type="number"
            stroke="var(--muted)"
            tickFormatter={(share: number) => formatPercent(share)}
          />
          <YAxis type="category" dataKey="name" stroke="var(--muted)" width={110} />
          <Tooltip
            formatter={(share, _name, item) =>
              `${formatPercent(Number(share))} · ${formatMoney(item.payload.ars, 'ARS')}`
            }
          />
          <Bar dataKey="share" name="Participación" fill="var(--accent)" radius={[0, 4, 4, 0]} maxBarSize={22}>
            <LabelList
              dataKey="share"
              position="right"
              fill="var(--muted)"
              formatter={(share) => formatPercent(Number(share))}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** One bar per month of the range, empty months included, so the axis reads as time. */
function DividendChart({ months, range, currency }: {
  months: MonthAmount[]
  range: { start: string; end: string }
  currency: Currency
}) {
  const key = currency === 'ARS' ? 'ars' : 'usd'
  const byMonth = new Map(months.map((m) => [m.month, Number(m[key])]))
  const data = monthsBetween(range.start, range.end).map((month) => ({
    month: formatMonth(month),
    value: byMonth.get(month) ?? 0,
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="month" stroke="var(--muted)" />
          <YAxis
            stroke="var(--muted)"
            width={90}
            tickFormatter={(value: number) => formatMoney(value, currency).replace(/,\d+$/, '')}
          />
          <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
          <Bar dataKey="value" name="Dividendos" fill="var(--income)" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function Dividends({ currency }: { currency: Currency }) {
  const [months, setMonths] = useState(12)
  const range = lastMonthsRange(months)
  const dividends = useDividends(range.start, range.end)
  const rows = dividends.data ?? []
  const total = rows.reduce((sum, m) => sum + Number(currency === 'ARS' ? m.ars : m.usd), 0)
  const picker = (
    <select value={months} onChange={(e) => setMonths(Number(e.target.value))} aria-label="Período">
      {RANGES.map((n) => (
        <option key={n} value={n}>
          Últimos {n} meses
        </option>
      ))}
    </select>
  )
  return (
    <Section title="Dividendos" actions={picker}>
      <ErrorNote error={dividends.error} />
      {dividends.data && rows.length === 0 && <Empty>No hay dividendos en el período.</Empty>}
      {rows.length > 0 && (
        <>
          <p>
            Total del período: <strong><Money value={total} currency={currency} /></strong>
            <span className="muted"> (neto de los gastos cobrados sobre cada dividendo)</span>
          </p>
          <DividendChart months={rows} range={range} currency={currency} />
          <h3>Por especie</h3>
          <DividendsByInstrument range={range} currency={currency} />
        </>
      )}
    </Section>
  )
}

export function Investments() {
  const [currency, setCurrency] = useState<Currency>('ARS')
  const portfolio = usePortfolio()
  const data = portfolio.data
  const empty = data && data.positions.length === 0 && data.cash.length === 0
  return (
    <>
      <Section title="Inversiones" actions={<CurrencyToggle value={currency} onChange={setCurrency} />}>
        <ErrorNote error={portfolio.error} />
        {empty && (
          <Empty>Importá un resumen de Balanz (posición consolidada o cuenta corriente) para ver tus inversiones.</Empty>
        )}
        {data && !empty && (
          <>
            <Totals portfolio={data} currency={currency} />
            {data.missing_price > 0 && (
              <p className="muted">{data.missing_price} posiciones sin precio no suman en el total.</p>
            )}
            <h3>Valor en el tiempo</h3>
            <History currency={currency} />
            <h3>Distribución</h3>
            <Allocation portfolio={data} />
            <h3>Posiciones</h3>
            <Positions portfolio={data} currency={currency} />
            <p className="muted small">
              La ganancia se calcula con costo promedio sobre las compras importadas. «Parcial» indica que
              parte de la tenencia es anterior al primer resumen de movimientos importado: importando
              resúmenes más viejos se completa.
            </p>
          </>
        )}
      </Section>
      <Dividends currency={currency} />
    </>
  )
}
