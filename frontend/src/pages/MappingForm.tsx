import { useState } from 'react'

import { send, useAccounts, useApiMutation } from '../api/hooks'
import type { Mapping, MappingInput, TabularMapping } from '../api/types'
import { ErrorNote } from '../components/ui'

const DEFAULT_CONFIG: TabularMapping = {
  header_row: 1,
  delimiter: null,
  date_column: 'Fecha',
  date_format: '%d/%m/%Y',
  description_columns: ['Concepto'],
  amount_column: 'Importe',
  debit_column: null,
  credit_column: null,
  decimal_separator: ',',
  thousands_separator: '.',
  negate: false,
}

type AmountMode = 'single' | 'split'

function TextField({ label, value, onChange, hint }: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
}) {
  return (
    <label>
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} />
      {hint && <small className="muted">{hint}</small>}
    </label>
  )
}

function AmountFields({ config, mode, update }: {
  config: TabularMapping
  mode: AmountMode
  update: (patch: Partial<TabularMapping>) => void
}) {
  if (mode === 'single') {
    return (
      <TextField
        label="Columna de importe"
        value={config.amount_column ?? ''}
        onChange={(v) => update({ amount_column: v })}
      />
    )
  }
  return (
    <>
      <TextField
        label="Columna débito"
        value={config.debit_column ?? ''}
        onChange={(v) => update({ debit_column: v || null })}
      />
      <TextField
        label="Columna crédito"
        value={config.credit_column ?? ''}
        onChange={(v) => update({ credit_column: v || null })}
      />
    </>
  )
}

/** Create or edit how one export source's columns map onto transactions. */
export function MappingForm({ existing, onDone }: { existing?: Mapping; onDone: () => void }) {
  const { data: accounts = [] } = useAccounts()
  const [name, setName] = useState(existing?.name ?? '')
  const [chosenAccountId, setAccountId] = useState(existing?.account_id ?? 0)
  const accountId = chosenAccountId || accounts[0]?.id || 0
  const [config, setConfig] = useState<TabularMapping>(existing?.config ?? DEFAULT_CONFIG)
  const [mode, setMode] = useState<AmountMode>(config.amount_column ? 'single' : 'split')
  const update = (patch: Partial<TabularMapping>) => setConfig({ ...config, ...patch })
  const save = useApiMutation((body: MappingInput) =>
    existing ? send('PUT', `/mappings/${existing.id}`, body) : send('POST', '/mappings', body),
  )

  const submit = () => {
    const amounts =
      mode === 'single'
        ? { debit_column: null, credit_column: null }
        : { amount_column: null }
    save.mutate({ name, account_id: accountId, config: { ...config, ...amounts } }, { onSuccess: onDone })
  }

  if (accounts.length === 0) {
    return <p className="muted">Primero creá una cuenta en la pestaña Cuentas.</p>
  }
  return (
    <div className="form-grid">
      <TextField label="Nombre del formato" value={name} onChange={setName} hint="Ej.: Santander CA pesos" />
      <label>
        Cuenta destino
        <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Fila del encabezado
        <input
          type="number"
          min={1}
          value={config.header_row}
          onChange={(e) => update({ header_row: Number(e.target.value) })}
        />
      </label>
      <TextField label="Columna de fecha" value={config.date_column} onChange={(v) => update({ date_column: v })} />
      <TextField
        label="Formato de fecha"
        value={config.date_format}
        onChange={(v) => update({ date_format: v })}
        hint="%d/%m/%Y = 31/01/2026"
      />
      <TextField
        label="Columnas de descripción"
        value={config.description_columns.join(', ')}
        onChange={(v) => update({ description_columns: v.split(',').map((s) => s.trim()).filter(Boolean) })}
        hint="Separadas por coma; se unen en una sola descripción"
      />
      <label>
        Importes
        <select value={mode} onChange={(e) => setMode(e.target.value as AmountMode)}>
          <option value="single">Una columna con signo</option>
          <option value="split">Columnas débito y crédito</option>
        </select>
      </label>
      <AmountFields config={config} mode={mode} update={update} />
      <TextField
        label="Separador decimal"
        value={config.decimal_separator}
        onChange={(v) => update({ decimal_separator: v })}
      />
      <TextField
        label="Separador de miles"
        value={config.thousands_separator}
        onChange={(v) => update({ thousands_separator: v })}
      />
      <label className="check">
        <input type="checkbox" checked={config.negate} onChange={(e) => update({ negate: e.target.checked })} />
        Invertir signos (resúmenes de tarjeta con compras positivas)
      </label>
      <div className="actions">
        <button onClick={submit} disabled={!name.trim()}>
          Guardar formato
        </button>
        <button className="secondary" onClick={onDone}>
          Cancelar
        </button>
      </div>
      <ErrorNote error={save.error} />
    </div>
  )
}
