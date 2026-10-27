import { useState } from 'react'

import { send, useAccounts, useApiMutation, useCategories, useRules } from '../api/hooks'
import type { CategoryInput, TransactionKind } from '../api/types'
import { Empty, ErrorNote, Section } from '../components/ui'
import { KIND_LABELS } from '../lib/format'

const SIGN_LABELS = { any: 'cualquier signo', debit: 'solo débitos', credit: 'solo créditos' }

function CategoryForm() {
  const [form, setForm] = useState<CategoryInput>({ name: '', kind: null })
  const create = useApiMutation((body: CategoryInput) => send('POST', '/categories', body))
  return (
    <div className="inline-form">
      <input placeholder="Nueva categoría" value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <select
        value={form.kind ?? ''}
        onChange={(e) => setForm({ ...form, kind: (e.target.value || null) as TransactionKind | null })}
        aria-label="Tipo forzado"
      >
        <option value="">Tipo según el signo</option>
        {Object.entries(KIND_LABELS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            Siempre {label.toLowerCase()}
          </option>
        ))}
      </select>
      <button
        disabled={!form.name.trim()}
        onClick={() => create.mutate(form, { onSuccess: () => setForm({ name: '', kind: null }) })}
      >
        Agregar
      </button>
      <ErrorNote error={create.error} />
    </div>
  )
}

function CategoryList() {
  const { data = [] } = useCategories()
  const remove = useApiMutation((id: number) => send('DELETE', `/categories/${id}`))
  if (data.length === 0) return <Empty>Sin categorías todavía.</Empty>
  return (
    <ul className="chips">
      {data.map((c) => (
        <li key={c.id}>
          {c.name}
          {c.kind && <span className="muted"> · {KIND_LABELS[c.kind]}</span>}
          <button className="link" aria-label={`Borrar ${c.name}`} onClick={() => remove.mutate(c.id)}>
            ×
          </button>
        </li>
      ))}
    </ul>
  )
}

function RuleList() {
  const { data: rules = [] } = useRules()
  const { data: categories = [] } = useCategories()
  const { data: accounts = [] } = useAccounts()
  const remove = useApiMutation((id: number) => send('DELETE', `/rules/${id}`))
  const apply = useApiMutation(() => send<{ categorized: number }>('POST', '/rules/apply'))
  const name = (id: number | null, list: { id: number; name: string }[]) =>
    list.find((item) => item.id === id)?.name ?? '—'

  return (
    <Section
      title="Reglas"
      actions={<button onClick={() => apply.mutate(undefined)}>Aplicar a movimientos sin categoría</button>}
    >
      {apply.data && <p className="success">{apply.data.categorized} movimientos categorizados.</p>}
      <p className="muted">
        Se crean desde Movimientos con «Regla…». Se aplican al importar, de menor a mayor prioridad.
      </p>
      {rules.length === 0 && <Empty>Sin reglas todavía.</Empty>}
      <table>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td>
                {r.match_type === 'regex' ? 'regex' : 'contiene'} <code>{r.pattern}</code>
              </td>
              <td>→ {name(r.category_id, categories)}</td>
              <td className="muted">
                {r.account_id ? name(r.account_id, accounts) : 'todas las cuentas'} · {SIGN_LABELS[r.sign]}
              </td>
              <td className="num">prioridad {r.priority}</td>
              <td>
                <button className="link" onClick={() => remove.mutate(r.id)}>
                  Borrar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  )
}

export function Categories() {
  return (
    <>
      <Section title="Categorías">
        <p className="muted">
          Una categoría con tipo forzado (por ejemplo «Compra MEP» como cambio) saca sus
          movimientos de ingresos y gastos.
        </p>
        <CategoryForm />
        <CategoryList />
      </Section>
      <RuleList />
    </>
  )
}
