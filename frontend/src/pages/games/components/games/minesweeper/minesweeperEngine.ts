/**
 * Minesweeper game engine — pure logic, no React.
 *
 * Handles board generation, cell reveal (with flood fill),
 * flagging, and win detection.
 */

export interface Cell {
  isMine: boolean
  isRevealed: boolean
  isFlagged: boolean
  adjacentMines: number
}

export type MineBoard = Cell[][]

/** Get adjacent cell coordinates. */
export function getAdjacentCells(row: number, col: number, rows: number, cols: number): [number, number][] {
  const adj: [number, number][] = []
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue
      const nr = row + dr
      const nc = col + dc
      if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
        adj.push([nr, nc])
      }
    }
  }
  return adj
}

/** Count mines adjacent to a cell. */
export function countAdjacentMines(board: MineBoard, row: number, col: number): number {
  const rows = board.length
  const cols = board[0].length
  return getAdjacentCells(row, col, rows, cols)
    .filter(([r, c]) => board[r][c].isMine)
    .length
}

/** Generate a board with mines, ensuring safe cell and its neighbors are mine-free. */
export function generateBoard(rows: number, cols: number, mines: number, safeRow: number, safeCol: number): MineBoard {
  // Create empty board
  const board: MineBoard = Array.from({ length: rows }, () =>
    Array.from({ length: cols }, () => ({
      isMine: false,
      isRevealed: false,
      isFlagged: false,
      adjacentMines: 0,
    }))
  )

  // Determine safe zone (safe cell + neighbors)
  const safeZone = new Set<string>()
  safeZone.add(`${safeRow},${safeCol}`)
  for (const [r, c] of getAdjacentCells(safeRow, safeCol, rows, cols)) {
    safeZone.add(`${r},${c}`)
  }

  // Place mines randomly
  let placed = 0
  const totalCells = rows * cols
  const maxMines = Math.min(mines, totalCells - safeZone.size)

  while (placed < maxMines) {
    const r = Math.floor(Math.random() * rows)
    const c = Math.floor(Math.random() * cols)
    if (!board[r][c].isMine && !safeZone.has(`${r},${c}`)) {
      board[r][c].isMine = true
      placed++
    }
  }

  // Calculate adjacent mine counts
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!board[r][c].isMine) {
        board[r][c].adjacentMines = countAdjacentMines(board, r, c)
      }
    }
  }

  return board
}

/** Clone a board. */
function cloneBoard(board: MineBoard): MineBoard {
  return board.map(row => row.map(cell => ({ ...cell })))
}

/** Reveal a cell. If it's blank (0 adjacent mines), flood fill. Returns whether a mine was hit. */
export function revealCell(board: MineBoard, row: number, col: number): { board: MineBoard; hitMine: boolean } {
  const newBoard = cloneBoard(board)
  const cell = newBoard[row][col]

  if (cell.isRevealed || cell.isFlagged) {
    return { board: newBoard, hitMine: false }
  }

  cell.isRevealed = true

  if (cell.isMine) {
    return { board: newBoard, hitMine: true }
  }

  // Flood fill for blank cells
  if (cell.adjacentMines === 0) {
    const rows = board.length
    const cols = board[0].length
    const stack: [number, number][] = getAdjacentCells(row, col, rows, cols)

    while (stack.length > 0) {
      const [r, c] = stack.pop()!
      const neighbor = newBoard[r][c]
      if (neighbor.isRevealed || neighbor.isFlagged || neighbor.isMine) continue

      neighbor.isRevealed = true
      if (neighbor.adjacentMines === 0) {
        stack.push(...getAdjacentCells(r, c, rows, cols))
      }
    }
  }

  return { board: newBoard, hitMine: false }
}

/** Toggle flag on a cell. Only works on hidden cells. */
export function toggleFlag(board: MineBoard, row: number, col: number): MineBoard {
  const newBoard = cloneBoard(board)
  const cell = newBoard[row][col]
  if (!cell.isRevealed) {
    cell.isFlagged = !cell.isFlagged
  }
  return newBoard
}

/** Check if all non-mine cells are revealed. */
export function checkWin(board: MineBoard): boolean {
  return board.flat().every(cell => cell.isMine || cell.isRevealed)
}
