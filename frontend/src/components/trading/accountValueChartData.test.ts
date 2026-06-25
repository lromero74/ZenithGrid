import { describe, it, expect } from 'vitest'
import { buildAccountValueSeries, type AccountValueSnapshot } from './accountValueChartData'

const snap = (over: Partial<AccountValueSnapshot> & { date: string }): AccountValueSnapshot => ({
  timestamp: `${over.date}T00:00:00Z`,
  total_value_btc: 1,
  total_value_usd: 100,
  ...over,
})

const HISTORY: AccountValueSnapshot[] = [
  snap({ date: '2026-06-01', total_value_btc: 1.0, total_value_usd: 100, btc_portion_btc: 0.6, usd_portion_usd: 40 }),
  snap({ date: '2026-06-02', total_value_btc: 1.1, total_value_usd: 110, btc_portion_btc: 0.7, usd_portion_usd: 45 }),
]

describe('buildAccountValueSeries', () => {
  it('total mode maps total values', () => {
    const { btcData, usdData } = buildAccountValueSeries(HISTORY, 'total', null, null, '2026-06-02')
    expect(btcData).toEqual([
      { time: '2026-06-01', value: 1.0 },
      { time: '2026-06-02', value: 1.1 },
    ])
    expect(usdData.map(p => p.value)).toEqual([100, 110])
  })

  it('total mode appends a live point when the last snapshot is not today', () => {
    const { btcData, usdData } = buildAccountValueSeries(HISTORY, 'total', 1.25, 130, '2026-06-03')
    expect(btcData[btcData.length - 1]).toEqual({ time: '2026-06-03', value: 1.25 })
    expect(usdData[usdData.length - 1]).toEqual({ time: '2026-06-03', value: 130 })
    expect(btcData).toHaveLength(3)
  })

  it('total mode does NOT append a live point when the last snapshot is already today', () => {
    const { btcData } = buildAccountValueSeries(HISTORY, 'total', 1.25, 130, '2026-06-02')
    expect(btcData).toHaveLength(2)
    expect(btcData[btcData.length - 1]).toEqual({ time: '2026-06-02', value: 1.1 })
  })

  it('total mode does NOT append when live values are missing', () => {
    const { btcData } = buildAccountValueSeries(HISTORY, 'total', null, 130, '2026-06-09')
    expect(btcData).toHaveLength(2)
  })

  it('split mode uses portion values and never appends a live point', () => {
    const { btcData, usdData } = buildAccountValueSeries(HISTORY, 'split', 1.25, 130, '2026-06-09')
    expect(btcData.map(p => p.value)).toEqual([0.6, 0.7])
    expect(usdData.map(p => p.value)).toEqual([40, 45])
    expect(btcData).toHaveLength(2) // no live point appended in split mode
  })

  it('split mode drops snapshots missing portion data', () => {
    const mixed: AccountValueSnapshot[] = [
      snap({ date: '2026-06-01', btc_portion_btc: 0.6, usd_portion_usd: 40 }),
      snap({ date: '2026-06-02' }), // no portion fields
    ]
    const { btcData } = buildAccountValueSeries(mixed, 'split', null, null, '2026-06-09')
    expect(btcData).toEqual([{ time: '2026-06-01', value: 0.6 }])
  })

  it('empty history with no live values yields empty series', () => {
    const { btcData, usdData } = buildAccountValueSeries([], 'total', null, null, '2026-06-09')
    expect(btcData).toEqual([])
    expect(usdData).toEqual([])
  })

  it('empty history WITH live values yields just the live point (total mode)', () => {
    const { btcData, usdData } = buildAccountValueSeries([], 'total', 2, 222, '2026-06-09')
    expect(btcData).toEqual([{ time: '2026-06-09', value: 2 }])
    expect(usdData).toEqual([{ time: '2026-06-09', value: 222 }])
  })
})
