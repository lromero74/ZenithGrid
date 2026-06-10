/**
 * Tests for VirtualizedPositionList — windowed rendering of position rows so
 * only visible cards mount (the 100-per-page setting previously rendered all
 * 100 PositionCards and caused scroll jank).
 */

import { describe, test, expect, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { VirtualizedPositionList } from './VirtualizedPositionList'

const ROW_HEIGHT = 90

// jsdom has no layout: the virtualizer measures rendered rows via
// offsetHeight (0 in jsdom), so give every element a deterministic height
// matching the estimate.
const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => ROW_HEIGHT,
  })
})

afterEach(() => {
  if (originalOffsetHeight) {
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
  } else {
    delete (HTMLElement.prototype as { offsetHeight?: number }).offsetHeight
  }
})

interface Row {
  id: number
  label: string
}

function makeRows(n: number): Row[] {
  return Array.from({ length: n }, (_, i) => ({ id: i + 1, label: `position-${i + 1}` }))
}

function renderList(rows: Row[]) {
  return render(
    <VirtualizedPositionList
      items={rows}
      estimateSize={ROW_HEIGHT}
      getItemKey={(index) => rows[index].id}
      renderItem={(row) => <div data-testid="row">{row.label}</div>}
    />
  )
}

describe('VirtualizedPositionList', () => {
  test('renders every item when the list is small', () => {
    renderList(makeRows(5))
    expect(screen.getAllByTestId('row')).toHaveLength(5)
    expect(screen.getByText('position-1')).toBeTruthy()
    expect(screen.getByText('position-5')).toBeTruthy()
  })

  test('renders only a window of a 100-item list', () => {
    renderList(makeRows(100))
    const rendered = screen.getAllByTestId('row')
    expect(rendered.length).toBeGreaterThan(0)
    expect(rendered.length).toBeLessThan(100)
    // The window starts at the top of the (unscrolled) list
    expect(screen.getByText('position-1')).toBeTruthy()
  })

  test('renders rows in order starting from the first item', () => {
    renderList(makeRows(100))
    const labels = screen.getAllByTestId('row').map((el) => el.textContent)
    expect(labels[0]).toBe('position-1')
    const indices = labels.map((l) => Number(String(l).replace('position-', '')))
    const sorted = [...indices].sort((a, b) => a - b)
    expect(indices).toEqual(sorted)
  })

  test('reserves full scroll height for all items', () => {
    const { container } = renderList(makeRows(100))
    const wrapper = container.firstElementChild as HTMLElement
    expect(parseInt(wrapper.style.height, 10)).toBeGreaterThanOrEqual(ROW_HEIGHT * 100)
  })

  test('renders nothing for an empty list without crashing', () => {
    renderList([])
    expect(screen.queryAllByTestId('row')).toHaveLength(0)
  })
})
