// Where the owner stands in the monotributo: the last 12 months against the category's cap,
// the next recategorization, monthly invoicing, and the invoices with their PDFs.

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { send, uploadFile, useApiMutation, useInvoices, useMonotributoStatus } from '../api/hooks'
import type { ImportBatch, Invoice, MonotributoStatus } from '../api/types'
import { Empty, ErrorNote, Money, Section } from '../components/ui'
import { formatDate, formatMoney, formatMonth, formatPercent, monthsBetween } from '../lib/format'

const LEVEL_MESSAGES: Record<string, string> = {
  '0.8': 'Ya facturaste el 80 % del tope de tu categoría en los últimos 12 meses.',
  '0.9': 'Ya facturaste el 90 % del tope de tu categoría en los últimos 12 meses.',
  '1': 'Superaste el tope de tu categoría en los últimos 12 meses: te corresponde una categoría mayor.',
}

function CategoryPicker({ status }: { status: MonotributoStatus }) {
  const save = useApiMutation((letter: string) => send('PUT', '/monotributo/profile', { category: letter }))
  return (
    <label className="check">
      Tu categoría
      <select
        aria-label="Tu categoría"
        value={status.category?.letter ?? ''}
        onChange={(e) => e.target.value && save.mutate(e.target.value)}
      >
        <option value="">Elegí…</option>
        {status.categories.map((c) => (
          <option key={c.letter} value={c.letter}>
            {c.letter}
          </option>
        ))}
      </select>
      <ErrorNote error={save.error} />
    </label>
  )
}

function Tiles({ status }: { status: MonotributoStatus }) {
  const { category } = status
  const tiles = [
    {
      label: `Facturado del ${formatDate(status.window_start)} al ${formatDate(status.window_end)}`,
      value: <Money value={status.income} currency="ARS" />,
    },
    {
      label: category ? `Tope de la categoría ${category.letter}` : 'Tope de tu categoría',
      value: category ? <Money value={category.annual_cap} currency="ARS" /> : 'elegí tu categoría',
    },
    {
      label: status.usage ? `Margen (usaste ${formatPercent(Number(status.usage))})` : 'Margen',
      value: status.margin ? <Money value={status.margin} currency="ARS" /> : '—',
    },
  ]
  return (
    <div className="tiles">
      {tiles.map((tile) => (
        <div className="tile" key={tile.label}>
          <span className="muted">{tile.label}</span>
          <strong>{tile.value}</strong>
        </div>
      ))}
    </div>
  )
}

function Recategorization({ status }: { status: MonotributoStatus }) {
  const { next } = status
  const highest = status.categories[status.categories.length - 1]
  return (
    <p>
      Próxima recategorización: hasta el <strong>{formatDate(next.deadline)}</strong>. Mira lo facturado del{' '}
      {formatDate(next.window_start)} al {formatDate(next.window_end)}:{' '}
      <Money value={next.income} currency="ARS" /> hasta hoy, que corresponde a{' '}
      {next.implied ? (
        <>
          la <strong>categoría {next.implied.letter}</strong> (cuota de servicios{' '}
          {formatMoney(next.implied.monthly_services, 'ARS')} por mes).
        </>
      ) : (
        <strong>más que el tope de la categoría {highest?.letter}: quedarías fuera del monotributo.</strong>
      )}
    </p>
  )
}

function MonthlyChart({ status }: { status: MonotributoStatus }) {
  const byMonth = new Map(status.monthly.map((m) => [m.month, Number(m.ars)]))
  const data = monthsBetween(status.window_start, status.window_end).map((month) => ({
    month: formatMonth(month),
    value: byMonth.get(month) ?? 0,
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="month" stroke="var(--muted)" />
          <YAxis
            stroke="var(--muted)"
            width={100}
            tickFormatter={(value: number) => formatMoney(value, 'ARS').replace(/,\d+$/, '')}
          />
          <Tooltip formatter={(value) => formatMoney(Number(value), 'ARS')} />
          <Bar dataKey="value" name="Facturado" fill="var(--income)" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

interface UploadResult {
  name: string
  error: string | null
}

async function attachAll(files: File[]): Promise<UploadResult[]> {
  const results: UploadResult[] = []
  for (const file of files) {
    try {
      await uploadFile<ImportBatch>('/imports', {}, file)
      results.push({ name: file.name, error: null })
    } catch (error) {
      results.push({ name: file.name, error: error instanceof Error ? error.message : String(error) })
    }
  }
  return results
}

function PdfUploader() {
  const attach = useApiMutation(attachAll)
  return (
    <div className="inline-form">
      <label>
        Adjuntar PDFs de comprobantes
        <input
          type="file"
          accept=".pdf"
          multiple
          onChange={(e) => e.target.files && attach.mutate([...e.target.files])}
        />
      </label>
      {attach.data && (
        <ul className="checks">
          {attach.data.map((r) => (
            <li key={r.name} className={r.error ? 'check-fail' : 'check-ok'}>
              {r.error ? '✗' : '✓'} {r.name}
              {r.error && <span className="muted"> ({r.error})</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function InvoiceTable({ invoices }: { invoices: Invoice[] }) {
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
        </tr>
      </thead>
      <tbody>
        {invoices.map((i) => (
          <tr key={i.id}>
            <td>{formatDate(i.issued_on)}</td>
            <td>
              {i.type_label} <code>{i.number}</code>
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
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Monotributo() {
  const status = useMonotributoStatus()
  const invoices = useInvoices()
  const data = status.data
  const message = data?.level ? LEVEL_MESSAGES[String(Number(data.level))] : null
  return (
    <>
      <Section title="Monotributo" actions={data && <CategoryPicker status={data} />}>
        <ErrorNote error={status.error} />
        {message && (
          <p className="banner warning" role="alert">
            {message}
          </p>
        )}
        {data && (
          <>
            <Tiles status={data} />
            <Recategorization status={data} />
            <h3>Facturado por mes</h3>
            <MonthlyChart status={data} />
            <p className="muted small">
              Tabla de categorías de ARCA vigente desde el {formatDate(data.table_valid_from)}. Cuando ARCA la
              actualice, agregá la nueva en <code>monotributo/categories.json</code>.
            </p>
          </>
        )}
      </Section>
      <Section title="Comprobantes emitidos">
        <ErrorNote error={invoices.error} />
        {invoices.data?.length === 0 && (
          <Empty>Importá el CSV de “Mis Comprobantes – Emitidos” de ARCA desde Importar.</Empty>
        )}
        <PdfUploader />
        {invoices.data && invoices.data.length > 0 && <InvoiceTable invoices={invoices.data} />}
      </Section>
    </>
  )
}
