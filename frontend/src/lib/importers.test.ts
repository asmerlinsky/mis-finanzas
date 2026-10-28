import { describe, expect, it } from 'vitest'

import { preview } from '../test-fixtures'
import { blockers, importerLabel, suggestedAccount, targetCurrency } from './importers'

describe('importer helpers', () => {
  it('labels known importers and passes unknown ones through', () => {
    expect(importerLabel('santander_visa_pdf')).toBe('Santander · resumen Visa (PDF)')
    expect(importerLabel('otro')).toBe('otro')
  })

  it('reads the currency from the target', () => {
    expect(targetCurrency('santander/visa/USD')).toBe('USD')
    expect(targetCurrency('mercadopago/ARS')).toBe('ARS')
  })

  it('suggests an account per target', () => {
    expect(suggestedAccount('santander/CA/ARS')).toEqual({
      name: 'Santander CA pesos', institution: 'Santander', kind: 'bank', currency: 'ARS',
    })
    expect(suggestedAccount('santander/visa/USD')).toMatchObject({
      name: 'Santander Visa dólares', kind: 'card', currency: 'USD',
    })
    expect(suggestedAccount('mercadopago/ARS')).toMatchObject({
      name: 'Mercado Pago pesos', kind: 'wallet',
    })
    expect(suggestedAccount('santander/amex/USD')).toMatchObject({
      name: 'Santander Amex dólares', kind: 'card', currency: 'USD',
    })
    expect(suggestedAccount('balanz/MEP/USD')).toMatchObject({
      name: 'Balanz MEP dólares', kind: 'broker', currency: 'USD',
    })
    expect(suggestedAccount('balanz/ARS')).toMatchObject({ name: 'Balanz pesos', kind: 'broker' })
  })
})

describe('blockers', () => {
  it('allows a clean preview', () => {
    expect(blockers(preview(), false, 1)).toEqual([])
  })

  it('names every reason the import is blocked', () => {
    const bad = preview({
      already_imported: true,
      unmapped_targets: ['santander/CA/ARS'],
      checks: [{ name: 'saldo', expected: '1', actual: '2', ok: false }],
      errors: [{ line_number: 3, message: 'fecha' }],
    })
    expect(blockers(bad, false, 0)).toHaveLength(5)
    expect(blockers(bad, true, 0)).toHaveLength(4) // errors skipped on purpose
  })

  it('explains an invoice PDF that lacks its rate or differs from its invoice', () => {
    const check = (name: string, ok: boolean) => ({ name, expected: '1', actual: ok ? '1' : '0', ok })
    const invoices = { invoices: 0, new: 0, changed: [], pdf_for: 'Factura E 00001-00000003' }
    const noRate = preview({
      importer: 'arca_invoice_pdf', invoices: { ...invoices, pdf_creates: true },
      checks: [check('tipo de cambio', false)],
    })
    expect(blockers(noRate, false, 0)).toEqual([
      'No se pudo leer el tipo de cambio del PDF, que hace falta para cargar una factura en ' +
        'dólares sin Mis Comprobantes.',
    ])
    const differs = preview({
      importer: 'arca_invoice_pdf', invoices: { ...invoices, pdf_creates: false },
      checks: [check('importe total', true), check('CAE', false)],
    })
    expect(blockers(differs, false, 0)).toEqual([
      'El PDF no coincide con su comprobante de Mis Comprobantes (ver lo marcado con ✗).',
    ])
  })

  it('lets a broker statement through with no new movements', () => {
    const investments = {
      as_of: '2026-10-27', source: 'tenencias' as const, positions: 1, cash: 0,
      operations: 0, new_operations: 0, replaces_snapshot: false,
    }
    expect(blockers(preview({ investments }), false, 0)).toEqual([])
  })
})
