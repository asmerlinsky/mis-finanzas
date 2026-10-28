// The portfolio's value over time: a dot on each holdings statement's date, and a line through
// the days valued with downloaded prices.

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useInvestmentHistory } from '../../api/hooks'
import type { Currency, HistoryPoint } from '../../api/types'
import { ErrorNote } from '../../components/ui'
import { formatDate, formatMoney } from '../../lib/format'

interface Row {
  label: string
  value: number | null
  source: HistoryPoint['source']
}

interface DotProps {
  cx?: number
  cy?: number
  payload?: Row
}

/** A dot only on statement dates: those are the values the broker itself printed. */
function StatementDot({ cx, cy, payload }: DotProps) {
  if (cx === undefined || cy === undefined || payload?.source !== 'resumen') return <g />
  return <circle cx={cx} cy={cy} r={4} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
}

export function History({ currency }: { currency: Currency }) {
  const history = useInvestmentHistory()
  const rows: Row[] = (history.data ?? []).map((p) => ({
    label: formatDate(p.date),
    value: currency === 'ARS' ? Number(p.ars) : p.usd === null ? null : Number(p.usd),
    source: p.source,
  }))
  if (history.data && rows.length === 0) return null
  return (
    <div className="chart">
      <ErrorNote error={history.error} />
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ right: 16 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" stroke="var(--muted)" minTickGap={24} />
          <YAxis
            stroke="var(--muted)"
            width={100}
            tickFormatter={(value: number) => formatMoney(value, currency).replace(/,\d+$/, '')}
          />
          <Tooltip
            formatter={(value, _name, item) =>
              `${formatMoney(Number(value), currency)}${item.payload.source === 'resumen' ? ' (resumen)' : ''}`
            }
          />
          <Line
            type="monotone"
            dataKey="value"
            name="Valor"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={StatementDot}
            activeDot={{ r: 5 }}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="muted small">
        Los puntos son los valores de cada resumen de tenencias; la línea, los días valuados con
        precios de mercado.
      </p>
    </div>
  )
}
