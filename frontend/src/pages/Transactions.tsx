import { useState } from 'react'

import {
  send,
  useAccounts,
  useApiMutation,
  useCategories,
  useTransactions,
  useTransferCandidates,
} from '../api/hooks'
import type {
  Category,
  RuleInput,
  Transaction,
  TransactionFilters,
  TransactionKind,
} from '../api/types'
import { Empty, ErrorNote, Money, Section } from '../components/ui'
import { formatDate, KIND_LABELS } from '../lib/format'
import { ExchangeCandidates } from './transactions/ExchangeCandidates'

const PAGE_SIZE = 100

export function TransferCandidates() {
  const { data } = useTransferCandidates()
  const link = useApiMutation((ids: { outgoing_id: number; incoming_id: number }) =>
    send('POST', '/transfers', ids),
  )
  const linkAll = useApiMutation(() => send<{ linked: number }>('POST', '/transfers/all'))
  if (!data || data.length === 0) return null
  const actions = (
    <button onClick={() => linkAll.mutate(undefined)} disabled={linkAll.isPending}>
      Confirmar todas
    </button>
  )
  return (
    <Section title={`Posibles transferencias entre tus cuentas (${data.length})`} actions={actions}>
      <p className="muted">
        Confirmalas para que no cuenten como ingreso ni gasto (por ejemplo, el pago de la tarjeta
        desde el banco).
      </p>
      <ErrorNote error={link.error ?? linkAll.error} />
      <table>
        <tbody>
          {data.map(({ outgoing, incoming, days_apart }) => (
            <tr key={`${outgoing.id}-${incoming.id}`}>
              <td>
                {formatDate(outgoing.date)} · {outgoing.account_name} → {incoming.account_name}
                {days_apart > 0 && <span className="muted"> ({days_apart} d)</span>}
              </td>
              <td>{outgoing.description}</td>
              <td className="num">
                <Money value={incoming.amount} currency={incoming.currency} />
              </td>
              <td>
                <button
                  onClick={() => link.mutate({ outgoing_id: outgoing.id, incoming_id: incoming.id })}
                >
                  Confirmar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  )
}

function RuleForm({ tx, categories, onDone }: {
  tx: Transaction
  categories: Category[]
  onDone: () => void
}) {
  const [pattern, setPattern] = useState(tx.description.toUpperCase())
  const [categoryId, setCategoryId] = useState(tx.category_id ?? categories[0]?.id ?? 0)
  const create = useApiMutation(async (rule: RuleInput) => {
    await send('POST', '/rules', rule)
    await send('POST', '/rules/apply')
  })
  const submit = () =>
    create.mutate(
      {
        category_id: categoryId, pattern, match_type: 'contains', account_id: null,
        sign: 'any', priority: 100,
      },
      { onSuccess: onDone },
    )
  return (
    <div className="inline-form">
      <label>
        Si la descripción contiene
        <input value={pattern} onChange={(e) => setPattern(e.target.value)} />
      </label>
      <label>
        categoría
        <select value={categoryId} onChange={(e) => setCategoryId(Number(e.target.value))}>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <button onClick={submit} disabled={!pattern.trim() || !categoryId}>
        Crear regla y aplicar
      </button>
      <button className="secondary" onClick={onDone}>
        Cancelar
      </button>
      <ErrorNote error={create.error} />
    </div>
  )
}

function CategoryCell({ tx, categories }: { tx: Transaction; categories: Category[] }) {
  const update = useApiMutation((categoryId: number | null) =>
    send('PATCH', `/transactions/${tx.id}`, { category_id: categoryId }),
  )
  const unlink = useApiMutation(() => send('DELETE', `/transfers/${tx.id}`))
  if (tx.transfer_pair_id !== null) {
    return (
      <button className="secondary" onClick={() => unlink.mutate(undefined)}>
        Desvincular
      </button>
    )
  }
  return (
    <select
      value={tx.category_id ?? ''}
      onChange={(e) => update.mutate(e.target.value ? Number(e.target.value) : null)}
      aria-label="Categoría"
    >
      <option value="">Sin categoría</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  )
}

function Filters({ filters, onChange }: {
  filters: TransactionFilters
  onChange: (next: TransactionFilters) => void
}) {
  const { data: accounts = [] } = useAccounts()
  const set = (patch: TransactionFilters) => onChange({ ...filters, ...patch, offset: 0 })
  return (
    <div className="controls wrap">
      <input
        placeholder="Buscar descripción"
        value={filters.search ?? ''}
        onChange={(e) => set({ search: e.target.value })}
      />
      <select
        value={filters.account_id ?? ''}
        onChange={(e) => set({ account_id: e.target.value ? Number(e.target.value) : undefined })}
      >
        <option value="">Todas las cuentas</option>
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
      <select
        value={filters.kind ?? ''}
        onChange={(e) => set({ kind: (e.target.value || undefined) as TransactionKind | undefined })}
      >
        <option value="">Todos los tipos</option>
        {Object.entries(KIND_LABELS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            {label}
          </option>
        ))}
      </select>
      <input type="date" value={filters.start ?? ''} onChange={(e) => set({ start: e.target.value })} />
      <input type="date" value={filters.end ?? ''} onChange={(e) => set({ end: e.target.value })} />
      <label className="check">
        <input
          type="checkbox"
          checked={filters.uncategorized ?? false}
          onChange={(e) => set({ uncategorized: e.target.checked })}
        />
        Sin categoría
      </label>
    </div>
  )
}

function TransactionRow({ tx, categories, onRule }: {
  tx: Transaction
  categories: Category[]
  onRule: () => void
}) {
  return (
    <tr>
      <td>{formatDate(tx.date)}</td>
      <td>{tx.account_name}</td>
      <td>{tx.description}</td>
      <td className="num">
        <Money value={tx.amount} currency={tx.currency} />
      </td>
      <td>{KIND_LABELS[tx.kind]}</td>
      <td>
        <CategoryCell tx={tx} categories={categories} />
      </td>
      <td>
        {tx.transfer_pair_id === null && (
          <button className="link" onClick={onRule}>
            Regla…
          </button>
        )}
      </td>
    </tr>
  )
}

export function Transactions() {
  const [filters, setFilters] = useState<TransactionFilters>({ limit: PAGE_SIZE, offset: 0 })
  const [ruleFor, setRuleFor] = useState<Transaction | null>(null)
  const { data, error } = useTransactions(filters)
  const { data: categories = [] } = useCategories()
  const offset = filters.offset ?? 0
  const page = (delta: number) => setFilters({ ...filters, offset: offset + delta * PAGE_SIZE })

  return (
    <>
      <TransferCandidates />
      <ExchangeCandidates />
      <Section title="Movimientos">
        <Filters filters={filters} onChange={setFilters} />
        <ErrorNote error={error} />
        {ruleFor && (
          <RuleForm key={ruleFor.id} tx={ruleFor} categories={categories} onDone={() => setRuleFor(null)} />
        )}
        {data && data.items.length === 0 && <Empty>No hay movimientos con estos filtros.</Empty>}
        {data && data.items.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Cuenta</th>
                <th>Descripción</th>
                <th className="num">Monto</th>
                <th>Tipo</th>
                <th>Categoría</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((tx) => (
                <TransactionRow key={tx.id} tx={tx} categories={categories} onRule={() => setRuleFor(tx)} />
              ))}
            </tbody>
          </table>
        )}
        {data && data.total > PAGE_SIZE && (
          <div className="pager">
            <button disabled={offset === 0} onClick={() => page(-1)}>
              Anterior
            </button>
            <span className="muted">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} de {data.total}
            </span>
            <button disabled={offset + PAGE_SIZE >= data.total} onClick={() => page(1)}>
              Siguiente
            </button>
          </div>
        )}
      </Section>
    </>
  )
}
