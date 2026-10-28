// Shared test data: invented values only.

import type { Preview } from './api/types'

/** A clean, importable preview; override what a test needs. */
export function preview(overrides: Partial<Preview> = {}): Preview {
  return {
    importer: 'santander_account_pdf',
    filename: 'resumen.pdf',
    already_imported: false,
    new_count: 1,
    duplicate_count: 0,
    near_duplicate_count: 0,
    targets: [{ target: 'santander/CA/ARS', account_id: 1, rows: 1 }],
    unmapped_targets: [],
    checks: [{ name: 'saldo total en pesos', expected: '10.00', actual: '10.00', ok: true }],
    metadata: {},
    rows: [],
    errors: [],
    ...overrides,
  }
}
