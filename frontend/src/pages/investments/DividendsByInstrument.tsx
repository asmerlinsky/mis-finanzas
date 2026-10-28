// Net dividends per instrument over the selected range: each dividend minus its fees.

import { useDividendsByInstrument } from '../../api/hooks'
import type { Currency } from '../../api/types'
import { ErrorNote, Money } from '../../components/ui'

export function DividendsByInstrument({ range, currency }: {
  range: { start: string; end: string }
  currency: Currency
}) {
  const found = useDividendsByInstrument(range.start, range.end)
  const rows = found.data ?? []
  if (rows.length === 0) return <ErrorNote error={found.error} />
  return (
    <table>
      <thead>
        <tr>
          <th>Especie</th>
          <th>Descripción</th>
          <th className="num">Pagos</th>
          <th className="num">Total</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((d) => (
          <tr key={d.ticker}>
            <td><code>{d.ticker}</code></td>
            <td>{d.name ?? <span className="muted">—</span>}</td>
            <td className="num">{d.payments}</td>
            <td className="num">
              <Money value={currency === 'ARS' ? d.ars : d.usd} currency={currency} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
