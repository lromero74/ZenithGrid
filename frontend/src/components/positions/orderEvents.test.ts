import { describe, test, expect } from 'vitest'
import { buildOrderEvents, type OrderEvent } from './orderEvents'
import type { Trade } from '../../types'

function trade(over: Partial<Trade>): Trade {
  return {
    id: 1, position_id: 1, timestamp: '2026-06-15T00:00:00Z', side: 'buy',
    quote_amount: 100, base_amount: 1, price: 100, trade_type: 'initial',
    order_id: null, dca_levels: 1, ...over,
  }
}

describe('buildOrderEvents', () => {
  test('empty trades -> no events', () => {
    expect(buildOrderEvents([])).toEqual([])
  })

  test('base order labeled and reasoned', () => {
    const ev = buildOrderEvents([trade({ id: 1, trade_type: 'initial', price: 100, base_amount: 1, quote_amount: 100 })])
    expect(ev).toHaveLength(1)
    expect(ev[0].label).toBe('Base order')
    expect(ev[0].reason).toBe('Opened position')
  })

  test('safety order shows % below average entry (long)', () => {
    const ev = buildOrderEvents([
      trade({ id: 1, timestamp: '2026-06-15T00:00:00Z', side: 'buy', trade_type: 'initial', price: 100, base_amount: 1, quote_amount: 100 }),
      trade({ id: 2, timestamp: '2026-06-15T01:00:00Z', side: 'buy', trade_type: 'dca', price: 90, base_amount: 1, quote_amount: 90 }),
    ])
    expect(ev[1].label).toBe('Safety order #1')
    // avg entry before SO was 100, fill at 90 => 10% below
    expect(ev[1].reason).toBe('10.00% below average entry')
  })

  test('safety order numbering continues and close is detected', () => {
    const ev = buildOrderEvents([
      trade({ id: 1, timestamp: '2026-06-15T00:00:00Z', side: 'buy', trade_type: 'initial', price: 100, base_amount: 1, quote_amount: 100 }),
      trade({ id: 2, timestamp: '2026-06-15T01:00:00Z', side: 'buy', trade_type: 'dca', price: 90, base_amount: 1, quote_amount: 90 }),
      trade({ id: 3, timestamp: '2026-06-15T02:00:00Z', side: 'buy', trade_type: 'dca', price: 80, base_amount: 1, quote_amount: 80 }),
      trade({ id: 4, timestamp: '2026-06-15T03:00:00Z', side: 'sell', trade_type: 'sell', price: 120, base_amount: 3, quote_amount: 360 }),
    ])
    expect(ev.map((e: OrderEvent) => e.label)).toEqual([
      'Base order', 'Safety order #1', 'Safety order #2', 'Position closed',
    ])
  })

  test('cascade trade (dca_levels>1) shows a range', () => {
    const ev = buildOrderEvents([
      trade({ id: 1, side: 'buy', trade_type: 'initial', price: 100, base_amount: 1, quote_amount: 100, timestamp: '2026-06-15T00:00:00Z' }),
      trade({ id: 2, side: 'buy', trade_type: 'dca', price: 80, base_amount: 2, quote_amount: 160, dca_levels: 2, timestamp: '2026-06-15T01:00:00Z' }),
    ])
    expect(ev[1].label).toBe('Safety orders #1–#2')
  })

  test('short position: safety order shows % above average entry', () => {
    const ev = buildOrderEvents([
      trade({ id: 1, side: 'sell', trade_type: 'initial', price: 100, base_amount: 1, quote_amount: 100, timestamp: '2026-06-15T00:00:00Z' }),
      trade({ id: 2, side: 'sell', trade_type: 'dca', price: 110, base_amount: 1, quote_amount: 110, timestamp: '2026-06-15T01:00:00Z' }),
    ])
    expect(ev[1].label).toBe('Safety order #1')
    expect(ev[1].reason).toBe('10.00% above average entry')
  })
})
