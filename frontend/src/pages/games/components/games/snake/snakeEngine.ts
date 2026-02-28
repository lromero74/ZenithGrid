/**
 * Snake game engine — pure functions, no React dependencies.
 */

export type Direction = 'UP' | 'DOWN' | 'LEFT' | 'RIGHT'

export interface Position {
  x: number
  y: number
}

const OPPOSITES: Record<Direction, Direction> = {
  UP: 'DOWN',
  DOWN: 'UP',
  LEFT: 'RIGHT',
  RIGHT: 'LEFT',
}

export function getNextHead(head: Position, direction: Direction): Position {
  switch (direction) {
    case 'UP': return { x: head.x, y: head.y - 1 }
    case 'DOWN': return { x: head.x, y: head.y + 1 }
    case 'LEFT': return { x: head.x - 1, y: head.y }
    case 'RIGHT': return { x: head.x + 1, y: head.y }
  }
}

export function moveSnake(snake: Position[], direction: Direction, growing: boolean): Position[] {
  const newHead = getNextHead(snake[0], direction)
  const newSnake = [newHead, ...snake]
  if (!growing) newSnake.pop()
  return newSnake
}

export function checkWallCollision(head: Position, gridSize: number): boolean {
  return head.x < 0 || head.x >= gridSize || head.y < 0 || head.y >= gridSize
}

export function checkSelfCollision(snake: Position[]): boolean {
  const [head, ...body] = snake
  return body.some(seg => seg.x === head.x && seg.y === head.y)
}

export function isOppositeDirection(current: Direction, next: Direction): boolean {
  return OPPOSITES[current] === next
}

export function wrapPosition(pos: Position, gridSize: number): Position {
  return {
    x: ((pos.x % gridSize) + gridSize) % gridSize,
    y: ((pos.y % gridSize) + gridSize) % gridSize,
  }
}

export function generateFood(snake: Position[], gridSize: number): Position {
  const occupied = new Set(snake.map(s => `${s.x},${s.y}`))
  let pos: Position
  do {
    pos = {
      x: Math.floor(Math.random() * gridSize),
      y: Math.floor(Math.random() * gridSize),
    }
  } while (occupied.has(`${pos.x},${pos.y}`))
  return pos
}

export function getSpeed(score: number): number {
  // Speed increases every 5 points, starting at 150ms, min 60ms
  return Math.max(60, 150 - Math.floor(score / 5) * 10)
}
