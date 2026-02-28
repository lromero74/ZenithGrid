/**
 * Nonogram (Picross) game engine — pure logic, no React.
 *
 * Handles clue generation, row/column validation,
 * and puzzle completion checking.
 */

export type CellState = 'filled' | 'empty' | 'unknown'
export type Grid = CellState[][]

export interface ClueSet {
  rowClues: number[][]
  colClues: number[][]
}

/** Generate row and column clues from a binary solution grid. */
export function generateClues(solution: number[][]): ClueSet {
  const rows = solution.length
  const cols = solution[0].length

  const rowClues: number[][] = []
  for (let r = 0; r < rows; r++) {
    rowClues.push(getRunLengths(solution[r]))
  }

  const colClues: number[][] = []
  for (let c = 0; c < cols; c++) {
    const col = solution.map(row => row[c])
    colClues.push(getRunLengths(col))
  }

  return { rowClues, colClues }
}

/** Get run lengths of consecutive 1s in an array. */
function getRunLengths(line: number[]): number[] {
  const runs: number[] = []
  let count = 0
  for (const val of line) {
    if (val === 1) {
      count++
    } else if (count > 0) {
      runs.push(count)
      count = 0
    }
  }
  if (count > 0) runs.push(count)
  return runs.length === 0 ? [0] : runs
}

/**
 * Validate a row against its clues.
 * 'unknown' cells are treated as empty for validation.
 */
export function validateRow(row: CellState[], clues: number[]): boolean {
  const binary = row.map(c => c === 'filled' ? 1 : 0)
  const runs = getRunLengths(binary)
  return arraysEqual(runs, clues)
}

/** Validate a column of the grid against its clues. */
export function validateColumn(grid: Grid, colIndex: number, clues: number[]): boolean {
  const col = grid.map(row => row[colIndex])
  return validateRow(col, clues)
}

/** Check if the puzzle is complete (all rows and columns match clues). */
export function isPuzzleComplete(grid: Grid, rowClues: number[][], colClues: number[][]): boolean {
  for (let r = 0; r < grid.length; r++) {
    if (!validateRow(grid[r], rowClues[r])) return false
  }
  for (let c = 0; c < grid[0].length; c++) {
    if (!validateColumn(grid, c, colClues[c])) return false
  }
  return true
}

/** Create an empty grid of given dimensions. */
export function createGrid(rows: number, cols: number): Grid {
  return Array.from({ length: rows }, () => Array(cols).fill('unknown') as CellState[])
}

/** Toggle a cell's state: unknown → filled → empty → unknown. */
export function toggleCell(grid: Grid, row: number, col: number): Grid {
  const newGrid = grid.map(r => [...r])
  const current = newGrid[row][col]
  if (current === 'unknown') newGrid[row][col] = 'filled'
  else if (current === 'filled') newGrid[row][col] = 'empty'
  else newGrid[row][col] = 'unknown'
  return newGrid
}

/** Set a cell to a specific state. */
export function setCell(grid: Grid, row: number, col: number, state: CellState): Grid {
  const newGrid = grid.map(r => [...r])
  newGrid[row][col] = state
  return newGrid
}

function arraysEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false
  return a.every((val, i) => val === b[i])
}
