import { useState } from 'react'

import { uploadFile, useAccounts, useApiMutation, useImports, useMappings } from '../api/hooks'
import type { Currency, ImportBatch, Mapping, Preview } from '../api/types'
import { Empty, ErrorNote, Money, Section } from '../components/ui'
import { formatDate, KIND_LABELS } from '../lib/format'
import { MappingForm } from './MappingForm'

function PreviewTable({ preview, currency }: { preview: Preview; currency: Currency }) {
  return (
    <>
      {preview.errors.length > 0 && (
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
      )}
      <table>
        <thead>
          <tr>
            <th>Línea</th>
            <th>Fecha</th>
            <th>Descripción</th>
            <th className="num">Monto</th>
            <th>Tipo</th>
            <th>Categoría</th>
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row) => (
            <tr key={row.line_number} className={row.duplicate ? 'duplicate' : ''}>
              <td>{row.line_number}</td>
              <td>{formatDate(row.date)}</td>
              <td>
                {row.description}
                {row.duplicate && <span className="tag">ya importado</span>}
              </td>
              <td className="num">
                <Money value={row.amount} currency={currency} />
              </td>
              <td>{KIND_LABELS[row.kind]}</td>
              <td>{row.category_name ?? <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function Uploader({ mapping, currency }: { mapping: Mapping; currency: Currency }) {
  const [file, setFile] = useState<File | null>(null)
  const [skipInvalid, setSkipInvalid] = useState(false)
  const preview = useApiMutation((f: File) =>
    uploadFile<Preview>('/imports/preview', { mapping_id: String(mapping.id) }, f),
  )
  const commit = useApiMutation((f: File) =>
    uploadFile<ImportBatch>(
      '/imports',
      { mapping_id: String(mapping.id), skip_invalid_rows: String(skipInvalid) },
      f,
    ),
  )
  const result = preview.data
  const canCommit =
    result && !result.already_imported && result.new_count > 0 && (result.errors.length === 0 || skipInvalid)

  const choose = (f: File | null) => {
    setFile(f)
    preview.reset()
    commit.reset()
    if (f) preview.mutate(f)
  }

  return (
    <>
      <input type="file" accept=".csv,.txt,.tsv,.xlsx,.xlsm" onChange={(e) => choose(e.target.files?.[0] ?? null)} />
      <ErrorNote error={preview.error ?? commit.error} />
      {commit.data && (
        <p className="success">
          Importadas {commit.data.rows_imported} filas ({commit.data.rows_duplicate} ya existían,
          {` ${commit.data.rows_skipped}`} con errores omitidas).
        </p>
      )}
      {result && !commit.data && (
        <>
          <p>
            <strong>{result.new_count}</strong> movimientos nuevos, {result.duplicate_count} ya
            importados{result.already_imported && ' — este archivo ya fue importado'}.
          </p>
          {result.errors.length > 0 && (
            <label className="check">
              <input type="checkbox" checked={skipInvalid} onChange={(e) => setSkipInvalid(e.target.checked)} />
              Importar igual, omitiendo las filas con errores
            </label>
          )}
          <button disabled={!canCommit || commit.isPending} onClick={() => file && commit.mutate(file)}>
            Importar {result.new_count} movimientos
          </button>
          <PreviewTable preview={result} currency={currency} />
        </>
      )}
    </>
  )
}

function History() {
  const { data = [] } = useImports()
  if (data.length === 0) return <Empty>Todavía no importaste archivos.</Empty>
  return (
    <table>
      <thead>
        <tr>
          <th>Archivo</th>
          <th className="num">Importadas</th>
          <th className="num">Duplicadas</th>
          <th className="num">Omitidas</th>
        </tr>
      </thead>
      <tbody>
        {data.map((b) => (
          <tr key={b.id}>
            <td>{b.filename}</td>
            <td className="num">{b.rows_imported}</td>
            <td className="num">{b.rows_duplicate}</td>
            <td className="num">{b.rows_skipped}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Import() {
  const { data: mappings = [] } = useMappings()
  const { data: accounts = [] } = useAccounts()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editing, setEditing] = useState<'new' | 'edit' | null>(null)
  const selected = mappings.find((m) => m.id === selectedId) ?? mappings[0]
  const currency = accounts.find((a) => a.id === selected?.account_id)?.currency ?? 'ARS'

  const picker = (
    <div className="controls">
      {mappings.length > 0 && (
        <select value={selected?.id ?? ''} onChange={(e) => setSelectedId(Number(e.target.value))}>
          {mappings.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      )}
      {selected && (
        <button className="secondary" onClick={() => setEditing('edit')}>
          Editar formato
        </button>
      )}
      <button className="secondary" onClick={() => setEditing('new')}>
        Nuevo formato
      </button>
    </div>
  )

  return (
    <>
      <Section title="Importar movimientos (CSV o Excel)" actions={picker}>
        {editing && (
          <MappingForm
            key={editing === 'edit' ? selected?.id : 'new'}
            existing={editing === 'edit' ? selected : undefined}
            onDone={() => setEditing(null)}
          />
        )}
        {!editing && !selected && (
          <Empty>Creá un formato que indique qué columna es la fecha, la descripción y el importe.</Empty>
        )}
        {!editing && selected && <Uploader key={selected.id} mapping={selected} currency={currency} />}
      </Section>
      <Section title="Importaciones anteriores">
        <History />
      </Section>
    </>
  )
}
