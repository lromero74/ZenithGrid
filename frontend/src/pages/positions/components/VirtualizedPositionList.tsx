/**
 * Windowed list for position rows using @tanstack/react-virtual.
 *
 * The positions page scrolls with the window (no inner scroll container), so
 * this uses useWindowVirtualizer. Row heights vary (cards expand, group
 * headers appear), so rendered rows are measured dynamically via
 * measureElement; estimateSize only seeds unmeasured rows.
 */

import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'

interface VirtualizedPositionListProps<T> {
  items: T[]
  /** Estimated row height in px before a row is measured */
  estimateSize?: number
  /** Rows rendered beyond the visible window on each side */
  overscan?: number
  getItemKey: (index: number) => string | number
  renderItem: (item: T, index: number) => ReactNode
}

export function VirtualizedPositionList<T>({
  items,
  estimateSize = 90,
  overscan = 8,
  getItemKey,
  renderItem,
}: VirtualizedPositionListProps<T>) {
  const listRef = useRef<HTMLDivElement | null>(null)

  // listRef is null during the first render, so reading offsetTop inline always
  // yielded 0 → items were positioned relative to the viewport top instead of the
  // list's actual offset. Measure after mount (and on window resize) instead.
  const [scrollMargin, setScrollMargin] = useState(0)
  useLayoutEffect(() => {
    const measure = () => {
      if (listRef.current) setScrollMargin(listRef.current.offsetTop)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => estimateSize,
    overscan,
    scrollMargin,
    getItemKey,
  })

  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div
      ref={listRef}
      style={{
        height: `${virtualizer.getTotalSize()}px`,
        position: 'relative',
        width: '100%',
      }}
    >
      {virtualItems.map((virtualItem) => (
        <div
          key={virtualItem.key}
          data-index={virtualItem.index}
          ref={virtualizer.measureElement}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            transform: `translateY(${virtualItem.start - virtualizer.options.scrollMargin}px)`,
          }}
        >
          {renderItem(items[virtualItem.index], virtualItem.index)}
        </div>
      ))}
    </div>
  )
}
