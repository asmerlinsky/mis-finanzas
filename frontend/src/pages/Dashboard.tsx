import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useCategoryTotals, useMonthly } from '../api/hooks'
import type { CategoryTotal, Currency, MonthSummary } from '../api/types'
import { Empty, ErrorNote, Money, Section } from '../components/ui'
import { formatMoney, formatMonth, lastMonthsRange } from '../lib/format'

const RANGES = [3, 6, 12, 24]

function sum(rows: MonthSummary[], key: keyof MonthSummary): number {
  return rows.reduce((total, row) => total + Number(row[key]), 0)
}

function Totals({ months, currency }: { months: MonthSummary[]; currency: Currency }) {
  const suffix = currency === 'ARS' ? 'ars' : 'usd'
  const tiles = [
    { label: 'Ingresos', value: sum(months, `income_${suffix}`) },
    { label: 'Gastos', value: sum(months, `expense_${suffix}`) },
    { label: 'Resultado', value: sum(months, `net_${suffix}`) },
  ]
  return (
    <div className="tiles">
      {tiles.map((tile) => (
        <div className="tile" key={tile.label}>
          <span className="muted">{tile.label}</span>
          <strong>
            <Money value={tile.value} currency={currency} />
          </strong>
        </div>
      ))}
    </div>
  )
}

function MonthlyChart({ months, currency }: { months: MonthSummary[]; currency: Currency }) {
  const suffix = currency === 'ARS' ? 'ars' : 'usd'
  const data = months.map((m) => ({
    month: formatMonth(m.month),
    Ingresos: Number(m[`income_${suffix}`]),
    Gastos: Number(m[`expense_${suffix}`]),
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="month" stroke="var(--muted)" />
          <YAxis
            stroke="var(--muted)"
            width={90}
            tickFormatter={(value: number) => formatMoney(value, currency).replace(/,\d+$/, '')}
          />
          <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
          <Legend />
          <Bar dataKey="Ingresos" fill="var(--income)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Gastos" fill="var(--expense)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function CategoryTable({ totals }: { totals: CategoryTotal[] }) {
  if (totals.length === 0) return <Empty>No hay gastos en el período.</Empty>
  return (
    <table>
      <thead>
        <tr>
          <th>Categoría</th>
          <th className="num">ARS</th>
          <th className="num">USD MEP</th>
        </tr>
      </thead>
      <tbody>
        {totals.map((t) => (
          <tr key={t.category}>
            <td>{t.category}</td>
            <td className="num">
              <Money value={t.ars} currency="ARS" />
            </td>
            <td className="num">
              <Money value={t.usd} currency="USD" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Dashboard() {
  const [months, setMonths] = useState(12)
  const [currency, setCurrency] = useState<Currency>('ARS')
  const { start, end } = lastMonthsRange(months)
  const monthly = useMonthly(start, end)
  const categories = useCategoryTotals(start, end)
  const missing = (monthly.data ?? []).reduce((n, m) => n + m.missing_rate, 0)

  const controls = (
    <div className="controls">
      <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
        {RANGES.map((n) => (
          <option key={n} value={n}>
            Últimos {n} meses
          </option>
        ))}
      </select>
      <div className="toggle" role="group" aria-label="Moneda">
        {(['ARS', 'USD'] as const).map((c) => (
          <button key={c} className={c === currency ? 'active' : ''} onClick={() => setCurrency(c)}>
            {c === 'USD' ? 'USD MEP' : c}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <>
      <Section title="Ingresos y gastos" actions={controls}>
        <ErrorNote error={monthly.error} />
        {monthly.data && monthly.data.length === 0 && <Empty>No hay movimientos en el período.</Empty>}
        {monthly.data && monthly.data.length > 0 && (
          <>
            <Totals months={monthly.data} currency={currency} />
            <MonthlyChart months={monthly.data} currency={currency} />
          </>
        )}
        {missing > 0 && (
          <p className="muted">
            {missing} movimientos sin cotización MEP para su fecha no suman en los totales en la
            otra moneda.
          </p>
        )}
      </Section>
      <Section title="Gastos por categoría">
        <ErrorNote error={categories.error} />
        {categories.data && <CategoryTable totals={categories.data} />}
      </Section>
    </>
  )
}
