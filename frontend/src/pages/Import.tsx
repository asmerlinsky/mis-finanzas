import { useState } from 'react'

import {
  send,
  sourceAccountPath,
  uploadFile,
  useAccounts,
  useApiMutation,
  useImports,
  useMappings,
} from '../api/hooks'
import type { Account, ImportBatch, Preview } from '../api/types'
import { Empty, ErrorNote, Section } from '../components/ui'
import { importerLabel, suggestedAccount } from '../lib/importers'
import { type CommitOptions, ImportPreview } from './import/ImportPreview'
import { MappingForm } from './MappingForm'

const ACCEPTED = '.csv,.txt,.tsv,.xlsx,.xlsm,.pdf'

interface Mapped {
  target: string
  accountId: number
}

function mapTarget({ target, accountId }: Mapped) {
  return send('PUT', sourceAccountPath(target), { account_id: accountId })
}

async function createAndMap(target: string) {
  const account = await send<Account>('POST', '/accounts', suggestedAccount(target))
  await mapTarget({ target, accountId: account.id })
}

/** Upload, preview, map targets, commit. `mappingId` null = let the app detect the format. */
function Uploader({ mappingId }: { mappingId: number | null }) {
  const [file, setFile] = useState<File | null>(null)
  const { data: accounts = [] } = useAccounts()
  const fields: Record<string, string> = mappingId === null ? {} : { mapping_id: String(mappingId) }
  const preview = useApiMutation((f: File) => uploadFile<Preview>('/imports/preview', fields, f))
  const map = useApiMutation(mapTarget)
  const create = useApiMutation(createAndMap)
  const commit = useApiMutation(({ skipLines, skipInvalid }: CommitOptions) =>
    uploadFile<ImportBatch>(
      '/imports',
      { ...fields, skip_invalid_rows: String(skipInvalid), skip_lines: skipLines.join(',') },
      file as File,
    ),
  )
  const refresh = () => {
    if (file) preview.mutate(file)
  }
  const choose = (f: File | null) => {
    setFile(f)
    for (const mutation of [preview, map, create, commit]) mutation.reset()
    if (f) preview.mutate(f)
  }

  return (
    <>
      <input type="file" accept={ACCEPTED} onChange={(e) => choose(e.target.files?.[0] ?? null)} />
      <ErrorNote error={preview.error ?? map.error ?? create.error ?? commit.error} />
      {commit.data && (
        <p className="success">
          Importadas {commit.data.rows_imported} filas ({commit.data.rows_duplicate} ya existían,
          {` ${commit.data.rows_skipped}`} omitidas).
        </p>
      )}
      {preview.data && !commit.data && (
        <ImportPreview
          key={`${preview.data.filename}-${preview.data.unmapped_targets.join()}`}
          preview={preview.data}
          accounts={accounts}
          busy={preview.isPending || commit.isPending}
          onMap={(target, accountId) => map.mutate({ target, accountId }, { onSuccess: refresh })}
          onCreate={(target) => create.mutate(target, { onSuccess: refresh })}
          onCommit={(options) => commit.mutate(options)}
        />
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
          <th>Leído como</th>
          <th className="num">Importadas</th>
          <th className="num">Duplicadas</th>
          <th className="num">Omitidas</th>
        </tr>
      </thead>
      <tbody>
        {data.map((b) => (
          <tr key={b.id}>
            <td>{b.filename}</td>
            <td>{importerLabel(b.importer)}</td>
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
  const [mappingId, setMappingId] = useState<number | null>(null)
  const [editing, setEditing] = useState<'new' | 'edit' | null>(null)
  const selected = mappings.find((m) => m.id === mappingId)

  const picker = (
    <div className="controls">
      <select
        aria-label="Cómo leer el archivo"
        value={mappingId ?? ''}
        onChange={(e) => setMappingId(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Detectar automáticamente</option>
        {mappings.map((m) => (
          <option key={m.id} value={m.id}>
            Formato: {m.name}
          </option>
        ))}
      </select>
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
      <Section title="Importar movimientos" actions={picker}>
        <p className="muted">
          Los resúmenes de Santander (cuenta, Visa, Excel de movimientos) y de Mercado Pago se
          reconocen solos. Para otros archivos CSV o Excel, creá un formato de columnas.
        </p>
        {editing && (
          <MappingForm
            key={editing === 'edit' ? selected?.id : 'new'}
            existing={editing === 'edit' ? selected : undefined}
            onDone={() => setEditing(null)}
          />
        )}
        {!editing && <Uploader key={mappingId ?? 'detect'} mappingId={mappingId} />}
      </Section>
      <Section title="Importaciones anteriores">
        <History />
      </Section>
    </>
  )
}
