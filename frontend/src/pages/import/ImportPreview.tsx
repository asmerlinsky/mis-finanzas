// What an import will do, before it's written: which importer read the file, the statement's
// own checks, which account each part of the statement goes to, and every row.

import { useState } from 'react'

import type { Account, Currency, InvestmentSummary, Preview, PreviewRow, StatementCheck } from '../../api/types'
import { Money } from '../../components/ui'
import { formatDate, KIND_LABELS } from '../../lib/format'
import { blockers, DEFAULT_TARGET, importerLabel, suggestedAccount, targetCurrency } from '../../lib/importers'

export interface CommitOptions {
  skipLines: number[]
  skipInvalid: boolean
}

interface Props {
  preview: Preview
  accounts: Account[]
  busy: boolean
  onMap: (target: string, accountId: number) => void
  onCreate: (target: string) => void
  onCommit: (options: CommitOptions) => void
}

function Checks({ checks }: { checks: StatementCheck[] }) {
  if (checks.length === 0) return null
  return (
    <ul className="checks">
      {checks.map((check) => (
        <li key={check.name} className={check.ok ? 'check-ok' : 'check-fail'}>
          {check.ok ? '✓' : '✗'} {check.name}
          {!check.ok && (
            <span className="muted">
              {' '}
              (el resumen dice {check.expected}, se leyó {check.actual})
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function Targets({ preview, accounts, onMap, onCreate }: Pick<Props, 'preview' | 'accounts' | 'onMap' | 'onCreate'>) {
  const targets = preview.targets.filter((t) => t.target !== DEFAULT_TARGET)
  if (targets.length === 0) return null
  return (
    <table className="targets">
      <thead>
        <tr>
          <th>Parte del resumen</th>
          <th className="num">Filas</th>
          <th>Cuenta</th>
        </tr>
      </thead>
      <tbody>
        {targets.map(({ target, account_id, rows }) => {
          const currency = targetCurrency(target)
          const options = accounts.filter((a) => a.currency === currency)
          return (
            <tr key={target}>
              <td>
                <code>{target}</code>
              </td>
              <td className="num">{rows}</td>
              <td className="target-account">
                <select
                  aria-label={`Cuenta para ${target}`}
                  value={account_id ?? ''}
                  onChange={(e) => e.target.value && onMap(target, Number(e.target.value))}
                >
                  <option value="">Elegí una cuenta…</option>
                  {options.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                {account_id === null && (
                  <button className="link" onClick={() => onCreate(target)}>
                    Crear «{suggestedAccount(target).name}»
                  </button>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** A broker statement's positions and operations, stored along with its movements. */
function Investments({ summary }: { summary: InvestmentSummary | null }) {
  if (!summary) return null
  const date = summary.as_of ? ` al ${formatDate(summary.as_of)}` : ''
  const holdings = summary.source === 'tenencias'
  return (
    <p>
      {holdings ? 'Tenencias' : 'Instrumentos'}
      {date}: <strong>{summary.positions}</strong> posiciones
      {summary.cash > 0 && `, ${summary.cash} saldos en monedas`}
      {summary.operations > 0 && `, ${summary.operations} operaciones (${summary.new_operations} nuevas)`}.
      {summary.replaces_snapshot && (
        <span className="muted"> Reemplaza lo importado antes para esa fecha.</span>
      )}
    </p>
  )
}

function rowCurrency(row: PreviewRow, accounts: Account[]): Currency {
  return accounts.find((a) => a.id === row.account_id)?.currency ?? targetCurrency(row.target)
}

function Rows({ preview, accounts, skipped, toggle }: {
  preview: Preview
  accounts: Account[]
  skipped: Set<number>
  toggle: (line: number) => void
}) {
  const severalTargets = preview.targets.length > 1
  const accountName = (row: PreviewRow) =>
    accounts.find((a) => a.id === row.account_id)?.name ?? row.target
  return (
    <table>
      <thead>
        <tr>
          <th>Importar</th>
          <th>Fecha</th>
          {severalTargets && <th>Cuenta</th>}
          <th>Descripción</th>
          <th className="num">Monto</th>
          <th>Tipo</th>
          <th>Categoría</th>
        </tr>
      </thead>
      <tbody>
        {preview.rows.map((row) => (
          <tr key={row.line_number} className={row.duplicate ? 'duplicate' : row.near_duplicate ? 'near' : ''}>
            <td>
              {row.duplicate ? (
                <span className="muted">—</span>
              ) : (
                <input
                  type="checkbox"
                  aria-label={`Importar línea ${row.line_number}`}
                  checked={!skipped.has(row.line_number)}
                  onChange={() => toggle(row.line_number)}
                />
              )}
            </td>
            <td>{formatDate(row.date)}</td>
            {severalTargets && <td>{accountName(row)}</td>}
            <td>
              {row.description}
              {row.duplicate && <span className="tag">ya importado</span>}
              {row.near_duplicate && <span className="tag warn">posible duplicado</span>}
              {row.installment && <span className="tag">cuota {row.installment}</span>}
            </td>
            <td className="num">
              <Money value={row.amount} currency={rowCurrency(row, accounts)} />
            </td>
            <td>{KIND_LABELS[row.kind]}</td>
            <td>{row.category_name ?? <span className="muted">—</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Errors({ preview }: { preview: Preview }) {
  if (preview.errors.length === 0) return null
  return (
    <div className="error">
      <strong>{preview.errors.length} filas con errores:</strong>
      <ul>
        {preview.errors.slice(0, 20).map((e) => (
          <li key={e.line_number}>
            Línea {e.line_number}: {e.message}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ImportPreview({ preview, accounts, busy, onMap, onCreate, onCommit }: Props) {
  const [skipped, setSkipped] = useState<Set<number>>(new Set())
  const [skipInvalid, setSkipInvalid] = useState(false)
  const toggle = (line: number) => {
    const next = new Set(skipped)
    if (next.has(line)) next.delete(line)
    else next.add(line)
    setSkipped(next)
  }
  const importable = preview.rows.filter((r) => !r.duplicate && !skipped.has(r.line_number)).length
  const reasons = blockers(preview, skipInvalid, importable)
  const metadata = Object.entries(preview.metadata)

  return (
    <div className="preview">
      <p>
        Leído como <strong>{importerLabel(preview.importer)}</strong>
        {metadata.length > 0 && (
          <span className="muted"> · {metadata.map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>
        )}
      </p>
      <Checks checks={preview.checks} />
      <Targets preview={preview} accounts={accounts} onMap={onMap} onCreate={onCreate} />
      <Investments summary={preview.investments} />
      {preview.rows.length > 0 && (
        <p>
          <strong>{preview.new_count}</strong> movimientos nuevos, {preview.duplicate_count} ya
          importados
          {preview.near_duplicate_count > 0 &&
            `, ${preview.near_duplicate_count} posibles duplicados (destildalos para no importarlos)`}
          .
        </p>
      )}
      <Errors preview={preview} />
      {preview.errors.length > 0 && (
        <label className="check">
          <input type="checkbox" checked={skipInvalid} onChange={(e) => setSkipInvalid(e.target.checked)} />
          Importar igual, omitiendo las filas con errores
        </label>
      )}
      {reasons.length > 0 && (
        <ul className="blockers">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <button
        disabled={reasons.length > 0 || busy}
        onClick={() => onCommit({ skipLines: [...skipped], skipInvalid })}
      >
        {preview.rows.length === 0 && preview.investments ? 'Importar tenencias' : `Importar ${importable} movimientos`}
      </button>
      {preview.rows.length > 0 && (
        <Rows preview={preview} accounts={accounts} skipped={skipped} toggle={toggle} />
      )}
    </div>
  )
}
