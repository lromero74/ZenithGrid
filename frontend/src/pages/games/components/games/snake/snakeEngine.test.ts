/**
 * Tests for Snake game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  getNextHead,
  moveSnake,
  checkWallCollision,
  checkSelfCollision,
  isOppositeDirection,
  wrapPosition,
  type Position,
} from './snakeEngine'

describe('getNextHead', () => {
  const head: Position = { x: 5, y: 5 }

  test('moves up', () => {
    expect(getNextHead(head, 'UP')).toEqual({ x: 5, y: 4 })
  })

  test('moves down', () => {
    expect(getNextHead(head, 'DOWN')).toEqual({ x: 5, y: 6 })
  })

  test('moves left', () => {
    expect(getNextHead(head, 'LEFT')).toEqual({ x: 4, y: 5 })
  })

  test('moves right', () => {
    expect(getNextHead(head, 'RIGHT')).toEqual({ x: 6, y: 5 })
  })
})

describe('moveSnake', () => {
  test('moves snake forward without growing', () => {
    const snake: Position[] = [{ x: 3, y: 3 }, { x: 2, y: 3 }, { x: 1, y: 3 }]
    const result = moveSnake(snake, 'RIGHT', false)
    expect(result).toEqual([{ x: 4, y: 3 }, { x: 3, y: 3 }, { x: 2, y: 3 }])
  })

  test('grows snake when growing is true', () => {
    const snake: Position[] = [{ x: 3, y: 3 }, { x: 2, y: 3 }]
    const result = moveSnake(snake, 'RIGHT', true)
    expect(result).toHaveLength(3)
    expect(result[0]).toEqual({ x: 4, y: 3 })
    expect(result[2]).toEqual({ x: 2, y: 3 }) // tail preserved
  })

  test('does not mutate original snake', () => {
    const snake: Position[] = [{ x: 3, y: 3 }, { x: 2, y: 3 }]
    moveSnake(snake, 'RIGHT', false)
    expect(snake).toHaveLength(2)
  })
})

describe('checkWallCollision', () => {
  const gridSize = 20

  test('returns false when inside grid', () => {
    expect(checkWallCollision({ x: 10, y: 10 }, gridSize)).toBe(false)
  })

  test('returns true when x < 0', () => {
    expect(checkWallCollision({ x: -1, y: 5 }, gridSize)).toBe(true)
  })

  test('returns true when x >= gridSize', () => {
    expect(checkWallCollision({ x: 20, y: 5 }, gridSize)).toBe(true)
  })

  test('returns true when y < 0', () => {
    expect(checkWallCollision({ x: 5, y: -1 }, gridSize)).toBe(true)
  })

  test('returns true when y >= gridSize', () => {
    expect(checkWallCollision({ x: 5, y: 20 }, gridSize)).toBe(true)
  })

  test('returns false at boundary (0,0)', () => {
    expect(checkWallCollision({ x: 0, y: 0 }, gridSize)).toBe(false)
  })

  test('returns false at boundary (19,19)', () => {
    expect(checkWallCollision({ x: 19, y: 19 }, gridSize)).toBe(false)
  })
})

describe('checkSelfCollision', () => {
  test('returns false when head does not overlap body', () => {
    const snake: Position[] = [{ x: 5, y: 5 }, { x: 4, y: 5 }, { x: 3, y: 5 }]
    expect(checkSelfCollision(snake)).toBe(false)
  })

  test('returns true when head overlaps body', () => {
    const snake: Position[] = [{ x: 4, y: 5 }, { x: 4, y: 5 }, { x: 3, y: 5 }]
    expect(checkSelfCollision(snake)).toBe(true)
  })
})

describe('isOppositeDirection', () => {
  test('UP and DOWN are opposite', () => {
    expect(isOppositeDirection('UP', 'DOWN')).toBe(true)
  })

  test('LEFT and RIGHT are opposite', () => {
    expect(isOppositeDirection('LEFT', 'RIGHT')).toBe(true)
  })

  test('UP and LEFT are not opposite', () => {
    expect(isOppositeDirection('UP', 'LEFT')).toBe(false)
  })

  test('same direction is not opposite', () => {
    expect(isOppositeDirection('UP', 'UP')).toBe(false)
  })
})

describe('wrapPosition', () => {
  const gridSize = 20

  test('wraps x below 0', () => {
    expect(wrapPosition({ x: -1, y: 5 }, gridSize)).toEqual({ x: 19, y: 5 })
  })

  test('wraps x at gridSize', () => {
    expect(wrapPosition({ x: 20, y: 5 }, gridSize)).toEqual({ x: 0, y: 5 })
  })

  test('wraps y below 0', () => {
    expect(wrapPosition({ x: 5, y: -1 }, gridSize)).toEqual({ x: 5, y: 19 })
  })

  test('wraps y at gridSize', () => {
    expect(wrapPosition({ x: 5, y: 20 }, gridSize)).toEqual({ x: 5, y: 0 })
  })

  test('does not wrap valid position', () => {
    expect(wrapPosition({ x: 10, y: 10 }, gridSize)).toEqual({ x: 10, y: 10 })
  })
})
