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
import { Queue, type QueueStatus, QueueSummary } from './import/Queue'
import { MappingForm } from './MappingForm'

const ACCEPTED = '.csv,.txt,.tsv,.xlsx,.xlsm,.pdf'

/** What a commit stored: ledger rows, or the records of a file that has none. */
function committedMessage(batch: ImportBatch, preview: Preview | undefined): string {
  if (preview && preview.rows.length === 0) {
    const invoices = preview.invoices
    if (invoices?.pdf_for && invoices.pdf_creates) {
      return `${invoices.pdf_for} cargado desde su PDF; se confirma al importar Mis Comprobantes.`
    }
    if (invoices?.pdf_for) return `PDF adjuntado a ${invoices.pdf_for}.`
    if (invoices) {
      return `Comprobantes importados: ${invoices.new} nuevos, ${invoices.changed.length} actualizados.`
    }
    if (preview.investments) return 'Tenencias importadas.'
  }
  return (
    `Importadas ${batch.rows_imported} filas (${batch.rows_duplicate} ya existían, ` +
    `${batch.rows_skipped} omitidas).`
  )
}

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

interface Queued {
  files: File[]
  statuses: QueueStatus[]
  index: number
}

const EMPTY_QUEUE: Queued = { files: [], statuses: [], index: 0 }

/** The queue after file `index` ends as `status`, moving on to the next file. */
function advance(queue: Queued, status: QueueStatus): Queued {
  const index = queue.index + 1
  const statuses = queue.statuses.map((s, i): QueueStatus => {
    if (i === queue.index) return status
    return i === index ? { kind: 'current' } : s
  })
  return { ...queue, statuses, index }
}

/** Upload one file or several, then review them one by one: preview, map targets, commit or
 * skip. Each preview is read when its turn comes, so it already counts what the files before
 * it imported. `mappingId` null = let the app detect the format. */
export function Uploader({ mappingId }: { mappingId: number | null }) {
  const [queue, setQueue] = useState<Queued>(EMPTY_QUEUE)
  const { data: accounts = [] } = useAccounts()
  const fields: Record<string, string> = mappingId === null ? {} : { mapping_id: String(mappingId) }
  const preview = useApiMutation((f: File) => uploadFile<Preview>('/imports/preview', fields, f))
  const map = useApiMutation(mapTarget)
  const create = useApiMutation(createAndMap)
  const commit = useApiMutation(({ file, skipLines, skipInvalid }: CommitOptions & { file: File }) =>
    uploadFile<ImportBatch>(
      '/imports',
      { ...fields, skip_invalid_rows: String(skipInvalid), skip_lines: skipLines.join(',') },
      file,
    ),
  )
  const file = queue.files[queue.index] ?? null
  const several = queue.files.length > 1
  const done = queue.files.length > 0 && file === null

  const show = (next: Queued) => {
    for (const mutation of [preview, map, create, commit]) mutation.reset()
    setQueue(next)
    const nextFile = next.files[next.index]
    if (nextFile) preview.mutate(nextFile)
  }
  const choose = (files: File[]) =>
    show({
      files,
      statuses: files.map((_, i): QueueStatus => (i === 0 ? { kind: 'current' } : { kind: 'pending' })),
      index: 0,
    })
  const skip = () => {
    const message = preview.error instanceof Error ? preview.error.message : null
    show(advance(queue, message ? { kind: 'failed', message } : { kind: 'skipped' }))
  }
  const refresh = () => {
    if (file) preview.mutate(file)
  }
  const onCommit = (options: CommitOptions) => {
    if (!file) return
    commit.mutate(
      { ...options, file },
      {
        onSuccess: (batch) =>
          show(advance(queue, { kind: 'imported', message: committedMessage(batch, preview.data) })),
      },
    )
  }
  const single = queue.statuses[0]

  return (
    <>
      <input
        type="file"
        multiple
        accept={ACCEPTED}
        aria-label="Archivos a importar"
        onChange={(e) => choose([...(e.target.files ?? [])])}
      />
      {several && <Queue names={queue.files.map((f) => f.name)} statuses={queue.statuses} />}
      {done && several && <QueueSummary statuses={queue.statuses} />}
      {done && !several && single?.kind === 'imported' && <p className="success">{single.message}</p>}
      <ErrorNote error={preview.error ?? map.error ?? create.error ?? commit.error} />
      {file && several && (
        <p className="controls">
          <strong>{file.name}</strong>
          <span className="muted">
            ({queue.index + 1} de {queue.files.length})
          </span>
          <button className="secondary" onClick={skip}>
            Saltear este archivo
          </button>
        </p>
      )}
      {file && preview.data && (
        <ImportPreview
          key={`${queue.index}-${preview.data.filename}-${preview.data.unmapped_targets.join()}`}
          preview={preview.data}
          accounts={accounts}
          busy={preview.isPending || commit.isPending}
          onMap={(target, accountId) => map.mutate({ target, accountId }, { onSuccess: refresh })}
          onCreate={(target) => create.mutate(target, { onSuccess: refresh })}
          onCommit={onCommit}
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
          Los resúmenes de Santander (cuenta, Visa, American Express, Excel de movimientos),
          Mercado Pago, Balanz y ARCA se reconocen solos. Para otros archivos CSV o Excel, creá un
          formato de columnas. Podés elegir varios archivos: se revisan de a uno.
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
