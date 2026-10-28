import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Portfolio, PositionValue } from '../../api/types'
import { Positions } from './Positions'

function position(over: Partial<PositionValue>): PositionValue {
  return {
    ticker: 'X', name: 'X', asset_class: 'Cedears', quantity: '1',
    price: { price: '100', date: '2026-10-28', origin: 'mercado' },
    value_ars: '100.00', value_usd: '0.10',
    coverage: null, cost_ars: null, cost_usd: null, gain_ars: null, gain_usd: null,
    ...over,
  }
}

const PORTFOLIO: Portfolio = {
  as_of: '2026-10-28', quantities_as_of: '2026-10-20', cash_as_of: '2026-10-20',
  total_ars: '1000.00', total_usd: '1.00', missing_price: 0,
  positions: [
    position({ ticker: 'AAA', name: 'Uno', value_ars: '200.00', coverage: '1', cost_ars: '150.00', cost_usd: '0.15', gain_ars: '50.00', gain_usd: '0.05' }),
    position({ ticker: 'BBB', name: 'Dos', value_ars: '500.00', coverage: '0.5', cost_ars: '200.00', cost_usd: '0.20', gain_ars: '50.00', gain_usd: '0.05' }),
    position({ ticker: 'CCC', name: 'Tres', asset_class: 'Acciones', value_ars: '200.00',
      price: { price: '100', date: '2026-10-10', origin: 'resumen' } }),
  ],
  cash: [{ label: 'Pesos', currency: 'ARS', amount: '100', value_ars: '100.00', value_usd: '0.10' }],
  allocation: [],
  cost_ars: '350.00', gain_ars: '100.00', cost_usd: '0.35', gain_usd: '0.10',
}

function rowOf(text: string): HTMLElement {
  return screen.getByText(text).closest('tr') as HTMLElement
}

describe('Positions', () => {
  it('groups by class with subtotals, weights, gains and old prices', () => {
    render(<Positions portfolio={PORTFOLIO} currency="ARS" />)
    expect(rowOf('Total Cedears')).toHaveTextContent('700,00')
    expect(rowOf('Total Cedears')).toHaveTextContent('70%')
    expect(rowOf('Total Monedas')).toHaveTextContent('10%')
    expect(rowOf('Dos')).toHaveTextContent('50%') // weight
    expect(rowOf('Dos')).toHaveTextContent('parcial (50%)')
    expect(rowOf('Uno')).toHaveTextContent('33,3%') // 50 over a cost of 150
    expect(rowOf('Tres')).toHaveTextContent('sin costo conocido')
    expect(rowOf('Total Acciones').lastElementChild).toHaveTextContent('—') // no known cost: no gain
    expect(rowOf('Total Cedears').lastElementChild).toHaveTextContent('100,00')
    expect(rowOf('Tres')).toHaveTextContent('precio viejo') // 18 days older than the newest
    expect(rowOf('Uno')).not.toHaveTextContent('precio viejo')
  })

  it('sorts within each class', async () => {
    render(<Positions portfolio={PORTFOLIO} currency="ARS" />)
    const order = () => screen.getAllByRole('code').map((c) => c.textContent)
    expect(order()).toEqual(['BBB', 'AAA', 'CCC']) // by value, largest first
    await userEvent.click(screen.getByRole('button', { name: /Especie/ }))
    expect(order()).toEqual(['AAA', 'BBB', 'CCC'])
  })
})
