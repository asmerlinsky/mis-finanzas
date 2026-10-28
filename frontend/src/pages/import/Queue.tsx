// A batch of files imported one by one: each file's status, and the one under review.

export type QueueStatus =
  | { kind: 'pending' }
  | { kind: 'current' }
  | { kind: 'imported'; message: string }
  | { kind: 'skipped' }
  | { kind: 'failed'; message: string }

const LABELS: Record<QueueStatus['kind'], string> = {
  pending: 'pendiente',
  current: 'revisando',
  imported: 'importado',
  skipped: 'salteado',
  failed: 'no se pudo leer',
}

function detail(status: QueueStatus): string | null {
  return status.kind === 'imported' || status.kind === 'failed' ? status.message : null
}

export function Queue({ names, statuses }: { names: string[]; statuses: QueueStatus[] }) {
  return (
    <ol className="queue">
      {names.map((name, index) => {
        const status = statuses[index]
        const text = detail(status)
        return (
          <li key={`${index}-${name}`} className={`queue-${status.kind}`}>
            <span className="queue-name">{name}</span>{' '}
            <span className="tag">{LABELS[status.kind]}</span>
            {text && <span className="muted small"> {text}</span>}
          </li>
        )
      })}
    </ol>
  )
}

export function QueueSummary({ statuses }: { statuses: QueueStatus[] }) {
  const count = (kind: QueueStatus['kind']) => statuses.filter((s) => s.kind === kind).length
  return (
    <p className="success">
      Listo: {count('imported')} importados, {count('skipped')} salteados
      {count('failed') > 0 && `, ${count('failed')} no se pudieron leer`}.
    </p>
  )
}
