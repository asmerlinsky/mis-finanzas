// Rule suggestions: the owner's uncategorized movements grouped by merchant, largest first.
// One click creates the rule (and the category, if new) and applies it.

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, queryString } from '../../api/client'
import { send, useApiMutation, useCategories, useRuleSuggestions } from '../../api/hooks'
import type { Category, RulePreview, RuleSuggestion } from '../../api/types'
import { Empty, ErrorNote, Money, Section } from '../../components/ui'
import { formatDate } from '../../lib/format'

const NEW = 'new'

interface CreateRule {
  pattern: string
  sign: RuleSuggestion['sign']
  categoryId: number | null
  newCategory: string
}

/** Create the category if it's new, then the rule, then apply it to uncategorized movements. */
async function createRule({ pattern, sign, categoryId, newCategory }: CreateRule) {
  let id = categoryId
  if (id === null) {
    id = (await send<Category>('POST', '/categories', { name: newCategory.trim(), kind: null })).id
  }
  const rule = { category_id: id, pattern, match_type: 'contains', account_id: null, sign, priority: 100 }
  await send('POST', '/rules', rule)
  return send<{ categorized: number }>('POST', '/rules/apply')
}

function usePreview(pattern: string | null, sign: RuleSuggestion['sign']) {
  return useQuery({
    queryKey: ['rule-preview', pattern, sign],
    queryFn: () => api<RulePreview>(`/rules/preview${queryString({ pattern, sign })}`),
    enabled: pattern !== null,
  })
}

function Counts({ preview }: { preview: RulePreview }) {
  return (
    <>
      categoriza {preview.would_categorize}
      {preview.conflicts > 0 && (
        <span className="tag warn">también coincide con {preview.conflicts} ya categorizados</span>
      )}
    </>
  )
}

function SuggestionRow({ suggestion, categories, onCreated }: {
  suggestion: RuleSuggestion
  categories: Category[]
  onCreated: (categorized: number) => void
}) {
  const [pattern, setPattern] = useState(suggestion.pattern)
  const [tested, setTested] = useState<string | null>(null)
  const [choice, setChoice] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const preview = usePreview(tested, suggestion.sign)
  const create = useApiMutation(createRule)
  const edited = pattern.trim() !== suggestion.pattern
  const counts = edited ? (tested === pattern.trim() ? preview.data : undefined) : suggestion
  const ready = pattern.trim() && (choice === NEW ? newCategory.trim() : choice)
  const submit = () =>
    create.mutate(
      {
        pattern: pattern.trim(),
        sign: suggestion.sign,
        categoryId: choice === NEW ? null : Number(choice),
        newCategory,
      },
      { onSuccess: (result) => onCreated(result.categorized) },
    )
  return (
    <tr>
      <td>
        <input aria-label={`Patrón ${suggestion.pattern}`} size={28} value={pattern}
          onChange={(e) => setPattern(e.target.value)} />
        <span className="tag">{suggestion.sign === 'debit' ? 'gasto' : 'ingreso'}</span>
        <div className="muted small">{suggestion.example}</div>
      </td>
      <td className="num">
        {suggestion.count}
        <div className="muted small">
          {formatDate(suggestion.first_date)} – {formatDate(suggestion.last_date)}
        </div>
      </td>
      <td className="num">
        <Money value={suggestion.total_ars} currency="ARS" />
        {suggestion.missing_rate > 0 && (
          <div className="muted small">{suggestion.missing_rate} sin cotización MEP</div>
        )}
        <div className="muted small">{suggestion.accounts.join(', ')}</div>
      </td>
      <td>
        {counts ? <Counts preview={counts} /> : tested === pattern.trim() && preview.isFetching ? '…' : (
          <button className="link" disabled={!pattern.trim()} onClick={() => setTested(pattern.trim())}>
            Probar
          </button>
        )}
      </td>
      <td className="target-account">
        <select aria-label={`Categoría para ${suggestion.pattern}`} value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">Elegí…</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
          <option value={NEW}>Nueva categoría…</option>
        </select>
        {choice === NEW && (
          <input aria-label="Nombre de la categoría" placeholder="Nombre" value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)} />
        )}
        <button disabled={!ready || create.isPending} onClick={submit}>
          Crear regla
        </button>
        <ErrorNote error={create.error} />
      </td>
    </tr>
  )
}

export function Suggestions() {
  const suggestions = useRuleSuggestions()
  const { data: categories = [] } = useCategories()
  const [categorized, setCategorized] = useState<number | null>(null)
  const rows = suggestions.data ?? []
  return (
    <Section title="Sugerencias">
      <p className="muted">
        Movimientos sin categoría agrupados por comercio, los de más plata primero. Cada regla
        se aplica a los movimientos sin categoría y a los que importes después.
      </p>
      <ErrorNote error={suggestions.error} />
      {categorized !== null && (
        <p className="success">Regla creada: {categorized} movimientos categorizados.</p>
      )}
      {suggestions.data && rows.length === 0 && <Empty>No hay movimientos sin categoría.</Empty>}
      {rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Patrón</th>
              <th className="num">Movimientos</th>
              <th className="num">Total</th>
              <th>Regla</th>
              <th>Categoría</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <SuggestionRow
                key={`${s.sign}-${s.pattern}`}
                suggestion={s}
                categories={categories}
                onCreated={setCategorized}
              />
            ))}
          </tbody>
        </table>
      )}
    </Section>
  )
}
