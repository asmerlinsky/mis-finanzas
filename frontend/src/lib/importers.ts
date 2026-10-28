// Display helpers for imports: importer names, statement targets and suggested accounts.

import type { AccountInput, AccountKind, Currency, Preview } from '../api/types'

const IMPORTER_LABELS: Record<string, string> = {
  generic_tabular: 'Formato de columnas',
  santander_movements_xlsx: 'Santander · últimos movimientos (Excel)',
  santander_account_pdf: 'Santander · resumen de cuenta (PDF)',
  santander_visa_pdf: 'Santander · resumen Visa (PDF)',
  mercadopago_account_csv: 'Mercado Pago · resumen de cuenta (CSV)',
}

const INSTITUTIONS: Record<string, string> = {
  santander: 'Santander',
  mercadopago: 'Mercado Pago',
  balanz: 'Balanz',
}

const PRODUCTS: Record<string, string> = { CA: 'CA', CC: 'CC', visa: 'Visa' }

export const DEFAULT_TARGET = 'default'

export function importerLabel(name: string): string {
  return IMPORTER_LABELS[name] ?? name
}

/** `santander/visa/USD` -> USD; anything not ending in /USD is pesos. */
export function targetCurrency(target: string): Currency {
  return target.endsWith('/USD') ? 'USD' : 'ARS'
}

function kindFor(institution: string, product: string | undefined): AccountKind {
  if (product === 'visa') return 'card'
  if (institution === 'mercadopago') return 'wallet'
  if (institution === 'balanz') return 'broker'
  return 'bank'
}

/** The account a target most likely belongs to: `santander/CA/ARS` -> "Santander CA pesos". */
export function suggestedAccount(target: string): AccountInput {
  const parts = target.split('/')
  const institution = parts[0]
  const product = parts.length > 2 ? parts[1] : undefined
  const currency = targetCurrency(target)
  const name = [
    INSTITUTIONS[institution] ?? institution,
    product ? (PRODUCTS[product] ?? product) : null,
    currency === 'USD' ? 'dólares' : 'pesos',
  ]
    .filter(Boolean)
    .join(' ')
  return { name, institution: INSTITUTIONS[institution] ?? institution, kind: kindFor(institution, product), currency }
}

/** Why the import can't run yet; empty when it can. */
export function blockers(preview: Preview, skipInvalid: boolean, importable: number): string[] {
  const reasons: string[] = []
  if (preview.already_imported) reasons.push('Este archivo ya fue importado.')
  if (preview.checks.some((c) => !c.ok)) {
    reasons.push('Los totales del resumen no coinciden con lo leído, así que no se importa.')
  }
  if (preview.unmapped_targets.length > 0) {
    reasons.push('Elegí una cuenta para cada parte del resumen.')
  }
  if (preview.errors.length > 0 && !skipInvalid) reasons.push('Hay filas con errores.')
  if (importable === 0) reasons.push('No hay movimientos nuevos para importar.')
  return reasons
}
