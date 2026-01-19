import { createChart, ColorType, IChartApi } from 'lightweight-charts'
import React from 'react'

/**
 * Factory function to create and manage oscillator charts (RSI, MACD, Stochastic)
 * Eliminates code duplication by providing a reusable chart creation pattern
 */
export function createOscillatorChart(
  containerRef: React.RefObject<HTMLDivElement | null>,
  mainChartRef: React.RefObject<IChartApi | null>,
  isCleanedUp: React.MutableRefObject<boolean>
): {
  chartInstance: IChartApi | null
  cleanup: () => void
  syncTimeScale: () => void
} {
  if (!containerRef.current || isCleanedUp.current) {
    return {
      chartInstance: null,
      cleanup: () => {},
      syncTimeScale: () => {}
    }
  }

  // Create oscillator chart with consistent styling
  const chart = createChart(containerRef.current, {
    layout: {
      background: { type: ColorType.Solid, color: '#0f172a' },
      textColor: '#94a3b8',
    },
    grid: {
      vertLines: { color: '#1e293b' },
      horzLines: { color: '#1e293b' },
    },
    width: containerRef.current.clientWidth,
    height: 120,
    timeScale: {
      timeVisible: true,
      borderColor: '#334155',
      fixLeftEdge: true,
      fixRightEdge: true,
    },
    rightPriceScale: {
      borderColor: '#334155',
      minimumWidth: 100,
    },
    handleScroll: false,
    handleScale: false,
  })

  // Set up time scale synchronization with main chart
  const syncTimeScale = () => {
    if (mainChartRef.current) {
      mainChartRef.current.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
        if (chart && timeRange) {
          chart.timeScale().setVisibleRange(timeRange)
        }
      })
    }
  }

  // Cleanup function to remove the chart
  const cleanup = () => {
    if (chart) {
      chart.remove()
    }
  }

  return {
    chartInstance: chart,
    cleanup,
    syncTimeScale
  }
}
