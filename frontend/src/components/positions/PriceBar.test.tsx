/**
 * Tests for PriceBar — specifically the safety-order label regression where deals
 * with 4+ SOs hid every middle SO label (only first + last rendered).
 */
import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PriceBar } from './PriceBar'

// Loose shapes — PriceBar reads a handful of fields with defaults.
const makePosition = () =>
  ({
    average_buy_price: 100,
    safety_orders_deployed: 0,
    direction: 'long',
    product_id: 'BASED1-USD',
    strategy_config_snapshot: {},
  }) as never

const strategyConfig = {
  max_safety_orders: 4,
  price_deviation: 2.5,
  safety_order_step_scale: 1.0,
  take_profit_percentage: 2,
}

describe('PriceBar safety-order labels', () => {
  test('renders every SO label with 4 levels (no middle labels hidden)', () => {
    render(
      <PriceBar
        position={makePosition()}
        currentPrice={99}
        pnl={{ currentPrice: 99, percent: -1 } as never}
        strategyConfig={strategyConfig}
        fundsUsedPercent={0}
      />
    )
    for (const n of [1, 2, 3, 4]) {
      expect(screen.getByText(`SO${n}`)).toBeTruthy()
    }
  })
})
