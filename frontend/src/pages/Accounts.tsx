import { useState } from 'react'

import { send, useAccounts, useApiMutation } from '../api/hooks'
import type { Account, AccountInput, AccountKind, Currency } from '../api/types'
import { Empty, ErrorNote, Section } from '../components/ui'
import { ACCOUNT_KIND_LABELS } from '../lib/format'

const EMPTY: AccountInput = { name: '', institution: '', kind: 'bank', currency: 'ARS' }

function AccountForm({ existing, onDone }: { existing?: Account; onDone: () => void }) {
  const [form, setForm] = useState<AccountInput>(existing ?? EMPTY)
  const save = useApiMutation((body: AccountInput) =>
    existing ? send('PUT', `/accounts/${existing.id}`, body) : send('POST', '/accounts', body),
  )
  const submit = () =>
    save.mutate(form, {
      onSuccess: () => {
        setForm(EMPTY)
        onDone()
      },
    })
  return (
    <div className="inline-form">
      <input placeholder="Nombre (ej. Santander CA pesos)" value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <input placeholder="Institución" value={form.institution}
        onChange={(e) => setForm({ ...form, institution: e.target.value })} />
      <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as AccountKind })}>
        {Object.entries(ACCOUNT_KIND_LABELS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            {label}
          </option>
        ))}
      </select>
      <select value={form.currency}
        onChange={(e) => setForm({ ...form, currency: e.target.value as Currency })}>
        <option value="ARS">ARS</option>
        <option value="USD">USD</option>
      </select>
      <button onClick={submit} disabled={!form.name.trim() || !form.institution.trim()}>
        {existing ? 'Guardar' : 'Agregar cuenta'}
      </button>
      {existing && (
        <button className="secondary" onClick={onDone}>
          Cancelar
        </button>
      )}
      <ErrorNote error={save.error} />
    </div>
  )
}

export function Accounts() {
  const { data = [] } = useAccounts()
  const [editing, setEditing] = useState<number | null>(null)
  const remove = useApiMutation((id: number) => send('DELETE', `/accounts/${id}`))
  return (
    <Section title="Cuentas">
      <AccountForm onDone={() => undefined} />
      <ErrorNote error={remove.error} />
      {data.length === 0 && <Empty>Agregá tus cuentas: banco, tarjetas, billeteras y brokers.</Empty>}
      <table>
        <tbody>
          {data.map((account) =>
            editing === account.id ? (
              <tr key={account.id}>
                <td colSpan={5}>
                  <AccountForm existing={account} onDone={() => setEditing(null)} />
                </td>
              </tr>
            ) : (
              <tr key={account.id}>
                <td>{account.name}</td>
                <td>{account.institution}</td>
                <td>{ACCOUNT_KIND_LABELS[account.kind]}</td>
                <td>{account.currency}</td>
                <td className="row-actions">
                  <button className="link" onClick={() => setEditing(account.id)}>
                    Editar
                  </button>
                  <button className="link" onClick={() => remove.mutate(account.id)}>
                    Borrar
                  </button>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </Section>
  )
}
