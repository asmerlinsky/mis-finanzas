// The issued invoices, each with its PDF and the incoming movement that paid it: linked, a
// suggestion to confirm, or chosen by hand from the movements that could have paid it.

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../../api/client'
import { send, useApiMutation } from '../../api/hooks'
import type { Invoice, InvoicePayment } from '../../api/types'
import { ErrorNote, Money } from '../../components/ui'
import { formatDate, formatMoney } from '../../lib/format'

const CREDIT_NOTES = new Set([13, 21])

function paymentText(p: InvoicePayment): string {
  return `${formatDate(p.date)} · ${p.account_name}`
}

function useLink(invoiceId: number) {
  return useApiMutation((transactionId: number) =>
    send('PUT', `/monotributo/invoices/${invoiceId}/payment`, { transaction_id: transactionId }),
  )
}

/** The movements that could have paid the invoice, the likeliest first; pick one. */
function PaymentChooser({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const candidates = useQuery({
    queryKey: ['payment-candidates', invoice.id],
    queryFn: () => api<InvoicePayment[]>(`/monotributo/invoices/${invoice.id}/candidates`),
  })
  const [chosen, setChosen] = useState('')
  const link = useLink(invoice.id)
  const found = candidates.data ?? []
  if (candidates.data && found.length === 0) {
    return (
      <span className="muted small">
        No hay ingresos en {invoice.currency} cerca de esa fecha.{' '}
        <button className="link" onClick={onClose}>
          Cerrar
        </button>
      </span>
    )
  }
  return (
    <span className="target-account">
      <select aria-label={`Movimiento para ${invoice.number}`} value={chosen} onChange={(e) => setChosen(e.target.value)}>
        <option value="">Elegí el movimiento…</option>
        {found.map((c) => (
          <option key={c.transaction_id} value={c.transaction_id}>
            {paymentText(c)} · {formatMoney(c.amount, c.currency)}
            {c.exact ? '' : ' (otro monto)'} · {c.description}
          </option>
        ))}
      </select>
      <button disabled={!chosen || link.isPending} onClick={() => link.mutate(Number(chosen))}>
        Vincular
      </button>
      <button className="link" onClick={onClose}>
        Cancelar
      </button>
      <ErrorNote error={candidates.error ?? link.error} />
    </span>
  )
}

function Linked({ invoice, payment }: { invoice: Invoice; payment: InvoicePayment }) {
  const unlink = useApiMutation(() => send('DELETE', `/monotributo/invoices/${invoice.id}/payment`))
  return (
    <span>
      <span className="check-ok">✓</span> {paymentText(payment)}
      {!payment.exact && (
        <span className="muted small"> ({formatMoney(payment.amount, payment.currency)})</span>
      )}{' '}
      <button className="link" onClick={() => unlink.mutate(undefined)}>
        desvincular
      </button>
    </span>
  )
}

function PaymentCell({ invoice }: { invoice: Invoice }) {
  const [choosing, setChoosing] = useState(false)
  const link = useLink(invoice.id)
  if (CREDIT_NOTES.has(invoice.type_code)) return <span className="muted">—</span>
  if (invoice.payment) return <Linked invoice={invoice} payment={invoice.payment} />
  if (choosing) return <PaymentChooser invoice={invoice} onClose={() => setChoosing(false)} />
  const suggestion = invoice.suggestion
  return (
    <span>
      {suggestion && (
        <>
          ¿{paymentText(suggestion)}?{' '}
          <button className="link" onClick={() => link.mutate(suggestion.transaction_id)}>
            Confirmar
          </button>
        </>
      )}
      <button className="link" onClick={() => setChoosing(true)}>
        {suggestion ? 'Elegir otro' : 'Elegir movimiento'}
      </button>
      <ErrorNote error={link.error} />
    </span>
  )
}

export function InvoiceTable({ invoices }: { invoices: Invoice[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Comprobante</th>
          <th>Receptor</th>
          <th className="num">Importe</th>
          <th className="num">Pesos</th>
          <th>PDF</th>
          <th>Cobro</th>
        </tr>
      </thead>
      <tbody>
        {invoices.map((i) => (
          <tr key={i.id}>
            <td>{formatDate(i.issued_on)}</td>
            <td>
              {i.type_label} <code>{i.number}</code>
              {i.source === 'pdf' && <span className="tag warn">solo PDF</span>}
            </td>
            <td>{i.receiver_name}</td>
            <td className="num">
              <Money value={i.total} currency={i.currency} />
            </td>
            <td className="num">
              <Money value={i.total_ars} currency="ARS" />
            </td>
            <td>
              {i.has_pdf ? (
                <a href={`/api/monotributo/invoices/${i.id}/pdf`} target="_blank" rel="noreferrer">
                  ver
                </a>
              ) : (
                <span className="muted">—</span>
              )}
            </td>
            <td>
              <PaymentCell invoice={i} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
