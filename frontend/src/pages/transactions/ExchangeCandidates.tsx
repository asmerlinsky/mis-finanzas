// Same-day currency exchanges between own accounts (dollars sold or bought through the bank),
// to link as one movement each. Both sides are already out of income and expenses.

import { send, useApiMutation, useExchangeCandidates } from '../../api/hooks'
import type { ExchangeCandidate } from '../../api/types'
import { ErrorNote, Money, Section } from '../../components/ui'
import { formatDate, formatMoney } from '../../lib/format'

function Rate({ candidate }: { candidate: ExchangeCandidate }) {
  return (
    <>
      {formatMoney(candidate.rate, 'ARS')} por dólar
      {candidate.mep && <span className="muted small"> (MEP {formatMoney(candidate.mep, 'ARS')})</span>}
    </>
  )
}

export function ExchangeCandidates() {
  const { data } = useExchangeCandidates()
  const link = useApiMutation((ids: { outgoing_id: number; incoming_id: number }) =>
    send('POST', '/exchanges', ids),
  )
  const linkAll = useApiMutation(() => send<{ linked: number }>('POST', '/exchanges/all'))
  if (!data || data.length === 0) return null
  const actions = (
    <button onClick={() => linkAll.mutate(undefined)} disabled={linkAll.isPending}>
      Vincular todos
    </button>
  )
  return (
    <Section title={`Posibles cambios de moneda (${data.length})`} actions={actions}>
      <p className="muted">
        Compras y ventas de dólares entre tus cuentas, el mismo día. Ya no cuentan como ingreso
        ni gasto; vincularlas las muestra como una sola operación, con su cotización.
      </p>
      <ErrorNote error={link.error ?? linkAll.error} />
      <table>
        <tbody>
          {data.map((c) => (
            <tr key={`${c.outgoing.id}-${c.incoming.id}`}>
              <td>
                {formatDate(c.outgoing.date)} · {c.outgoing.account_name} → {c.incoming.account_name}
              </td>
              <td className="num">
                <Money value={c.outgoing.amount} currency={c.outgoing.currency} /> →{' '}
                <Money value={c.incoming.amount} currency={c.incoming.currency} />
              </td>
              <td className="num">
                <Rate candidate={c} />
              </td>
              <td>
                <button onClick={() => link.mutate({ outgoing_id: c.outgoing.id, incoming_id: c.incoming.id })}>
                  Vincular
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  )
}
