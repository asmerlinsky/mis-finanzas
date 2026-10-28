// The next 6 months if each invoices the same as last month (or the owner's own amount), and
// a question when last month's invoicing differs from the owner's amount.

import { useState } from 'react'

import { send, useApiMutation } from '../../api/hooks'
import type { Currency, MonotributoProjection, MonotributoStatus } from '../../api/types'
import { ErrorNote, Money, Section } from '../../components/ui'
import { formatDate, formatMoney, formatMonth, formatPercent } from '../../lib/format'

const LEVELS: Record<string, string> = { '0.8': '80 %', '0.9': '90 %', '1': 'supera el tope' }

function useSetProjection() {
  return useApiMutation((body: { amount: string; currency: Currency }) =>
    send('PUT', '/monotributo/projection', body),
  )
}

/** Last month's invoicing differs from the owner's amount: use it, or keep the amount. */
function AskToUpdate({ projection }: { projection: MonotributoProjection }) {
  const save = useSetProjection()
  const { currency } = projection
  return (
    <p className="banner warning" role="alert">
      En {formatMonth(projection.last_month)} facturaste{' '}
      {formatMoney(projection.last_month_amount, currency)}, distinto de tu proyección de{' '}
      {formatMoney(projection.amount, currency)} por mes. ¿La actualizo?{' '}
      <button className="link" onClick={() => save.mutate({ amount: projection.last_month_amount, currency })}>
        Usar {formatMoney(projection.last_month_amount, currency)}
      </button>
      <button className="link" onClick={() => save.mutate({ amount: projection.amount, currency })}>
        Mantener {formatMoney(projection.amount, currency)}
      </button>
      <ErrorNote error={save.error} />
    </p>
  )
}

function AmountEditor({ projection, onDone }: { projection: MonotributoProjection; onDone: () => void }) {
  const [amount, setAmount] = useState(projection.amount)
  const [currency, setCurrency] = useState<Currency>(projection.currency)
  const save = useSetProjection()
  return (
    <span className="target-account">
      <input aria-label="Monto por mes" inputMode="decimal" size={10} value={amount}
        onChange={(e) => setAmount(e.target.value.replace(',', '.'))} />
      <select aria-label="Moneda de la proyección" value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}>
        <option value="USD">USD</option>
        <option value="ARS">ARS</option>
      </select>
      <button disabled={!/^\d+(\.\d+)?$/.test(amount)} onClick={() => save.mutate({ amount, currency }, { onSuccess: onDone })}>
        Guardar
      </button>
      <button className="link" onClick={onDone}>
        Cancelar
      </button>
      <ErrorNote error={save.error} />
    </span>
  )
}

function Assumption({ projection }: { projection: MonotributoProjection }) {
  const [editing, setEditing] = useState(false)
  const clear = useApiMutation(() => send('DELETE', '/monotributo/projection'))
  if (editing) return <AmountEditor projection={projection} onDone={() => setEditing(false)} />
  const { amount, currency, rate } = projection
  return (
    <p>
      Suponiendo <strong>{formatMoney(amount, currency)} por mes</strong>{' '}
      {projection.manual ? '(tu monto)' : `(lo facturado en ${formatMonth(projection.last_month)})`}
      {currency === 'USD' && <span className="muted"> a {formatMoney(rate, 'ARS')} por dólar</span>}.{' '}
      <button className="link" onClick={() => setEditing(true)}>
        Cambiar
      </button>
      {projection.manual && (
        <button className="link" onClick={() => clear.mutate(undefined)}>
          Usar lo del último mes
        </button>
      )}
    </p>
  )
}

function MonthsTable({ projection }: { projection: MonotributoProjection }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Mes</th>
          <th className="num">Facturado</th>
          <th className="num">Últimos 12 meses</th>
          <th className="num">Del tope</th>
          <th>Aviso</th>
        </tr>
      </thead>
      <tbody>
        {projection.months.map((m) => (
          <tr key={m.month} className={m.level === '1' ? 'near' : ''}>
            <td>{formatMonth(m.month)}</td>
            <td className="num"><Money value={m.invoiced} currency="ARS" /></td>
            <td className="num"><Money value={m.rolling} currency="ARS" /></td>
            <td className="num">{m.usage === null ? '—' : formatPercent(Number(m.usage))}</td>
            <td>{m.level ? <span className="tag warn">{LEVELS[String(Number(m.level))]}</span> : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Projection({ status }: { status: MonotributoStatus }) {
  const { projection } = status
  return (
    <Section title="Proyección a 6 meses">
      {projection.ask && <AskToUpdate projection={projection} />}
      <Assumption projection={projection} />
      {projection.first_over && status.category && (
        <p className="error">
          Con esta proyección superarías el tope de la categoría {status.category.letter} en{' '}
          {formatMonth(projection.first_over)}.
        </p>
      )}
      <MonthsTable projection={projection} />
      <p>
        En la recategorización del {formatDate(status.next.deadline)} corresponderías a{' '}
        {projection.implied ? (
          <strong>la categoría {projection.implied.letter}</strong>
        ) : (
          <strong>más que la categoría más alta</strong>
        )}{' '}
        (<Money value={projection.recategorization_income} currency="ARS" /> proyectado del{' '}
        {formatDate(status.next.window_start)} al {formatDate(status.next.window_end)}).
      </p>
    </Section>
  )
}
