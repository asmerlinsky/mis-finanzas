// Display helpers for imports: importer names, statement targets and suggested accounts.

import type { AccountInput, AccountKind, Currency, Preview } from '../api/types'

const IMPORTER_LABELS: Record<string, string> = {
  generic_tabular: 'Formato de columnas',
  santander_movements_xlsx: 'Santander · últimos movimientos (Excel)',
  santander_account_pdf: 'Santander · resumen de cuenta (PDF)',
  santander_visa_pdf: 'Santander · resumen Visa (PDF)',
  santander_amex_pdf: 'Santander · resumen American Express (PDF)',
  santander_amex_legacy_pdf: 'Santander · resumen American Express, formato anterior (PDF)',
  mercadopago_account_csv: 'Mercado Pago · resumen de cuenta (CSV)',
  balanz_movements_pdf: 'Balanz · cuenta corriente (PDF)',
  balanz_holdings_pdf: 'Balanz · posición consolidada (PDF)',
  arca_mis_comprobantes_csv: 'ARCA · Mis Comprobantes emitidos (CSV)',
  arca_invoice_pdf: 'ARCA · comprobante (PDF)',
}

const INSTITUTIONS: Record<string, string> = {
  santander: 'Santander',
  mercadopago: 'Mercado Pago',
  balanz: 'Balanz',
}

const PRODUCTS: Record<string, string> = { CA: 'CA', CC: 'CC', visa: 'Visa', amex: 'Amex', MEP: 'MEP', CABLE: 'cable' }

export const DEFAULT_TARGET = 'default'

export function importerLabel(name: string): string {
  return IMPORTER_LABELS[name] ?? name
}

/** `santander/visa/USD` -> USD; anything not ending in /USD is pesos. */
export function targetCurrency(target: string): Currency {
  return target.endsWith('/USD') ? 'USD' : 'ARS'
}

function kindFor(institution: string, product: string | undefined): AccountKind {
  if (product === 'visa' || product === 'amex') return 'card'
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

/** Why the failed checks block the import, in the words that fit the file. */
function failedChecksReason(preview: Preview): string {
  if (preview.importer === 'arca_invoice_pdf') {
    if (preview.invoices?.pdf_creates) {
      return (
        'No se pudo leer el tipo de cambio del PDF, que hace falta para cargar una factura en ' +
        'dólares sin Mis Comprobantes.'
      )
    }
    return 'El PDF no coincide con su comprobante de Mis Comprobantes (ver lo marcado con ✗).'
  }
  return 'Los totales del resumen no coinciden con lo leído, así que no se importa.'
}

/** Why the import can't run yet; empty when it can. */
export function blockers(preview: Preview, skipInvalid: boolean, importable: number): string[] {
  const reasons: string[] = []
  if (preview.already_imported) reasons.push('Este archivo ya fue importado.')
  if (preview.checks.some((c) => !c.ok)) reasons.push(failedChecksReason(preview))
  if (preview.unmapped_targets.length > 0) {
    reasons.push('Elegí una cuenta para cada parte del resumen.')
  }
  if (preview.errors.length > 0 && !skipInvalid) reasons.push('Hay filas con errores.')
  // Broker statements and ARCA files store their own records, even with no movements.
  const records = preview.investments !== null || preview.invoices !== null
  if (importable === 0 && !records) reasons.push('No hay movimientos nuevos para importar.')
  return reasons
}
