/**
 * Turn the flat list of position rows into "visual rows" for the deals list.
 *
 * The deals list can render in three view modes (table / card list / tiled
 * grid). All three are window-virtualized as a single vertical column of
 * variable-height blocks, so multi-column tiling is expressed by packing N
 * cards into one visual row rather than by a CSS grid the virtualizer can't see.
 *
 * Group headers always occupy their own full-width row and reset the current
 * tiling chunk, so cards from two different groups never share a row.
 */

export interface PositionRow<P extends { id: number | string }> {
  position: P
  groupKey: string | null
  showHeader: boolean
}

export type VisualRow<P extends { id: number | string }> =
  | { kind: 'header'; key: string; label: string }
  | { kind: 'cards'; key: string; items: PositionRow<P>[] }

/**
 * @param rows    Ordered position rows (already filtered/sorted/paginated).
 * @param columns Cards per visual row (>= 1). Values < 1 are clamped to 1.
 */
export function buildVisualRows<P extends { id: number | string }>(
  rows: PositionRow<P>[],
  columns: number,
): VisualRow<P>[] {
  const cols = Math.max(1, Math.floor(columns) || 1)
  const out: VisualRow<P>[] = []
  let chunk: PositionRow<P>[] = []

  const flush = () => {
    if (chunk.length > 0) {
      out.push({ kind: 'cards', key: `cards-${chunk[0].position.id}`, items: chunk })
      chunk = []
    }
  }

  for (const row of rows) {
    if (row.showHeader && row.groupKey != null) {
      flush()
      out.push({ kind: 'header', key: `header-${row.groupKey}`, label: row.groupKey })
    }
    chunk.push(row)
    if (chunk.length >= cols) flush()
  }
  flush()

  return out
}
