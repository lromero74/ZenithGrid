/**
 * Lode Runner — canvas-based puzzle-platformer.
 *
 * Features: keyboard + mobile d-pad controls, 10 progressive levels,
 * gold collection, brick digging, guard AI, responsive scaling.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  loadLevel, updateGame, nextLevel,
  GAME_WIDTH, GAME_HEIGHT, CELL, COLS, ROWS,
  Tile, BRICK_FILL_TIME,
  type AnimState, type GameState, type Input, type Player, type Guard,
} from './lodeRunnerEngine'
import { useGameState } from '../../../hooks/useGameState'
import { LEVEL_NAMES } from './lodeRunnerLevels'
import type { GameStatus } from '../../../types'

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const C_BG = '#0a0a1a'
const C_SOLID = '#4a4a5a'
const C_SOLID_EDGE = '#3a3a4a'
const C_LADDER = '#c89632'
const C_BAR = '#9ca3af'
const C_GOLD = '#fbbf24'
const C_GOLD_SHINE = '#fde68a'
const C_PLAYER_HUD = '#d4a017'
const C_HIDDEN = '#22c55e'
const C_HUD = '#ffffff'

// C64-style brick palette
const C_MORTAR = '#3d2517'
const C_BRICK_A = '#9b6840'
const C_BRICK_B = '#8b5830'
const C_BRICK_HI = '#b07848'
const C_BRICK_FILL_A = '#8b5e3c'
const C_BRICK_FILL_B = '#9b6840'

const DIG_BLAST_DURATION = 0.25

// ---------------------------------------------------------------------------
// C64-style brick rendering
// ---------------------------------------------------------------------------

/** Draw a C64-style offset brick pattern (3 rows of alternating bricks) */
function drawBrickPattern(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const bh = 8 // brick row height (3 × 8 = 24px cell)
  // Fill mortar base
  ctx.fillStyle = C_MORTAR
  ctx.fillRect(x, y, CELL, CELL)
  // Rows 0 and 2: two bricks side by side
  for (const ri of [0, 2]) {
    const by = y + ri * bh
    ctx.fillStyle = C_BRICK_A
    ctx.fillRect(x + 1, by + 1, CELL / 2 - 2, bh - 1)
    ctx.fillStyle = C_BRICK_HI
    ctx.fillRect(x + 1, by + 1, CELL / 2 - 2, 1)
    ctx.fillStyle = C_BRICK_B
    ctx.fillRect(x + CELL / 2 + 1, by + 1, CELL / 2 - 2, bh - 1)
    ctx.fillStyle = C_BRICK_HI
    ctx.fillRect(x + CELL / 2 + 1, by + 1, CELL / 2 - 2, 1)
  }
  // Row 1: offset — half brick, full brick, half brick
  const by = y + bh
  ctx.fillStyle = C_BRICK_B
  ctx.fillRect(x + 1, by + 1, CELL / 4 - 1, bh - 1)
  ctx.fillStyle = C_BRICK_HI
  ctx.fillRect(x + 1, by + 1, CELL / 4 - 1, 1)
  ctx.fillStyle = C_BRICK_A
  ctx.fillRect(x + CELL / 4 + 1, by + 1, CELL / 2 - 2, bh - 1)
  ctx.fillStyle = C_BRICK_HI
  ctx.fillRect(x + CELL / 4 + 1, by + 1, CELL / 2 - 2, 1)
  ctx.fillStyle = C_BRICK_B
  ctx.fillRect(x + 3 * CELL / 4 + 1, by + 1, CELL / 4 - 2, bh - 1)
  ctx.fillStyle = C_BRICK_HI
  ctx.fillRect(x + 3 * CELL / 4 + 1, by + 1, CELL / 4 - 2, 1)
}

/** Render dig blast effect — C64-style zap/spark at the brick being dug */
function drawDigBlast(ctx: CanvasRenderingContext2D, x: number, y: number, progress: number): void {
  const cx = x + CELL / 2
  const cy = y + CELL / 2
  const alpha = 1 - progress * progress
  ctx.save()
  ctx.globalAlpha = alpha
  // Central flash
  ctx.fillStyle = '#ffff66'
  const r = 4 + progress * 6
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()
  // Pixel sparks
  ctx.fillStyle = '#ffa500'
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2
    const dist = 3 + progress * CELL * 0.5
    ctx.fillRect(cx + Math.cos(angle) * dist - 1, cy + Math.sin(angle) * dist - 1, 2, 2)
  }
  // White-hot center
  ctx.fillStyle = '#ffffff'
  ctx.globalAlpha = alpha * 0.8
  ctx.beginPath()
  ctx.arc(cx, cy, 2 + progress * 2, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}

/** Render C64-style V-shaped stepped brick refill animation */
function drawBrickRefill(ctx: CanvasRenderingContext2D, x: number, y: number, frac: number): void {
  if (frac <= 0) return
  const px = 2
  const gw = Math.floor(CELL / px)
  const gh = Math.floor(CELL / px)
  const mid = (gw - 1) / 2
  for (let r = 0; r < gh; r++) {
    const distFromBottom = 1 - r / (gh - 1) // 1 at top, 0 at bottom
    for (let c = 0; c < gw; c++) {
      const distFromEdge = 1 - Math.abs(c - mid) / mid // 1 at center, 0 at edges
      // V-shape: bottom fills first, center-top fills last
      const threshold = distFromBottom * 0.5 + distFromEdge * distFromBottom * 0.5
      if (frac > threshold) {
        ctx.fillStyle = ((r + c) & 1) ? C_BRICK_FILL_A : C_BRICK_FILL_B
        ctx.fillRect(x + c * px, y + r * px, px, px)
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = C_BG
  ctx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT)
}

function drawTiles(ctx: CanvasRenderingContext2D, gs: GameState): void {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const tile = gs.grid[r][c]
      const x = c * CELL
      const y = r * CELL

      switch (tile) {
        case Tile.Brick: {
          const dug = gs.dugBricks.find(db => db.col === c && db.row === r)
          if (dug) {
            if (dug.phase === 'digging') {
              // A12: Brick partially dissolving from top to bottom
              const progress = 1 - dug.timer / DIG_BLAST_DURATION
              // Draw remaining brick (top portion erases as progress increases)
              const eraseRows = Math.floor(progress * CELL)
              if (eraseRows < CELL) {
                ctx.save()
                ctx.beginPath()
                ctx.rect(x, y + eraseRows, CELL, CELL - eraseRows)
                ctx.clip()
                drawBrickPattern(ctx, x, y)
                ctx.restore()
              }
              // Dig blast effect overlay
              drawDigBlast(ctx, x, y, progress)
            } else if (dug.phase === 'open') {
              // Empty — brick is open, nothing to draw
            } else if (dug.phase === 'filling') {
              // C64 V-shaped stepped refill
              drawBrickRefill(ctx, x, y, 1 - dug.timer / BRICK_FILL_TIME)
            }
          } else {
            // C64-style brick pattern
            drawBrickPattern(ctx, x, y)
          }
          break
        }
        case Tile.Solid:
          ctx.fillStyle = C_SOLID
          ctx.fillRect(x, y, CELL, CELL)
          ctx.strokeStyle = C_SOLID_EDGE
          ctx.lineWidth = 1
          ctx.strokeRect(x + 0.5, y + 0.5, CELL - 1, CELL - 1)
          // Cross pattern
          ctx.beginPath()
          ctx.moveTo(x, y)
          ctx.lineTo(x + CELL, y + CELL)
          ctx.moveTo(x + CELL, y)
          ctx.lineTo(x, y + CELL)
          ctx.stroke()
          break
        case Tile.Ladder:
          ctx.strokeStyle = C_LADDER
          ctx.lineWidth = 2
          // Sides
          ctx.beginPath()
          ctx.moveTo(x + 4, y)
          ctx.lineTo(x + 4, y + CELL)
          ctx.moveTo(x + CELL - 4, y)
          ctx.lineTo(x + CELL - 4, y + CELL)
          ctx.stroke()
          // Rungs
          ctx.lineWidth = 1.5
          for (let ry = 4; ry < CELL; ry += 6) {
            ctx.beginPath()
            ctx.moveTo(x + 4, y + ry)
            ctx.lineTo(x + CELL - 4, y + ry)
            ctx.stroke()
          }
          break
        case Tile.Bar:
          ctx.strokeStyle = C_BAR
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(x, y + CELL / 3)
          ctx.lineTo(x + CELL, y + CELL / 3)
          ctx.stroke()
          // Grip dots
          ctx.fillStyle = C_BAR
          ctx.beginPath()
          ctx.arc(x + CELL / 2, y + CELL / 3, 2, 0, Math.PI * 2)
          ctx.fill()
          break
        case Tile.Hidden:
          if (gs.escapeRevealed) {
            // Flashing green ladder
            const alpha = 0.6 + 0.4 * Math.sin(gs.animTime * 6)
            ctx.strokeStyle = C_HIDDEN
            ctx.globalAlpha = alpha
            ctx.lineWidth = 2
            ctx.beginPath()
            ctx.moveTo(x + 4, y)
            ctx.lineTo(x + 4, y + CELL)
            ctx.moveTo(x + CELL - 4, y)
            ctx.lineTo(x + CELL - 4, y + CELL)
            ctx.stroke()
            ctx.lineWidth = 1.5
            for (let ry = 4; ry < CELL; ry += 6) {
              ctx.beginPath()
              ctx.moveTo(x + 4, y + ry)
              ctx.lineTo(x + CELL - 4, y + ry)
              ctx.stroke()
            }
            ctx.globalAlpha = 1
          }
          break
      }
    }
  }
}

function drawGold(ctx: CanvasRenderingContext2D, gs: GameState): void {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (!gs.goldMap[r][c]) continue
      const cx = c * CELL + CELL / 2
      const cy = r * CELL + CELL / 2
      const sz = CELL / 2 - 2
      // Gold nugget
      ctx.fillStyle = C_GOLD
      ctx.beginPath()
      ctx.moveTo(cx, cy - sz)
      ctx.lineTo(cx + sz, cy)
      ctx.lineTo(cx, cy + sz)
      ctx.lineTo(cx - sz, cy)
      ctx.closePath()
      ctx.fill()
      // Shine
      ctx.fillStyle = C_GOLD_SHINE
      ctx.beginPath()
      ctx.arc(cx - 2, cy - 2, 2, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

// ---------------------------------------------------------------------------
// C64-style pixel-art sprite system
// ---------------------------------------------------------------------------

// Sprite frame: 8 cols x 12 rows, drawn at 2x = 16x24 within 24px cell
// Values: 0=transparent, 1=primary, 2=secondary, 3=detail
type Frame = number[][]

// Player palette (gold C64 runner)
const PLAYER_COLORS = ['#d4a017', '#f5d442', '#8b5e14']
// Guard palette (red C64 guard)
const GUARD_COLORS = ['#dc2626', '#fca5a5', '#fbbf24']

// --- Player frames ---
const P_STAND: Frame[] = [[
  [0,0,1,1,1,1,0,0],
  [0,0,1,2,2,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,1,1,1,1,1,1,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,3,3,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,0,0,1,0,0],
  [0,0,1,0,0,1,0,0],
  [0,1,1,0,0,1,1,0],
  [0,0,0,0,0,0,0,0],
]]

const P_RUN: Frame[] = [
  [ // stride right — head/torso lean right
    [0,0,0,1,1,1,1,0],
    [0,0,0,1,2,2,1,0],
    [0,0,0,0,1,1,0,0],
    [0,0,1,1,1,1,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,0,1,0,0],
    [0,0,1,0,0,0,1,0],
    [0,1,1,0,0,0,1,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // legs together — centered head
    [0,0,1,1,1,1,0,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,1,1,1,1,1,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // stride left — head/torso lean left
    [0,1,1,1,1,0,0,0],
    [0,1,2,2,1,0,0,0],
    [0,0,1,1,0,0,0,0],
    [0,1,1,1,1,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,0,1,0],
    [0,1,0,0,0,1,0,0],
    [0,1,0,0,1,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const P_CLIMB: Frame[] = [
  [ // right hand up
    [0,0,1,1,1,1,0,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,1,0,0],
    [0,0,1,1,1,0,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,1,0,0,0],
    [0,0,0,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // left hand up
    [0,0,1,1,1,1,0,0],
    [0,0,1,2,2,1,0,0],
    [0,0,1,1,0,0,0,0],
    [0,1,0,1,1,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,0,1,0,0],
    [0,0,1,0,0,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const P_HANG: Frame[] = [
  [ // right hand forward
    [0,0,1,1,1,1,1,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // left hand forward
    [0,1,1,1,1,1,0,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const P_FALL: Frame[] = [[
  [0,1,0,0,0,0,1,0],
  [0,0,1,0,0,1,0,0],
  [0,0,1,1,1,1,0,0],
  [0,0,1,2,2,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,3,3,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,0,0,0,0,0],
]]

const P_DIG: Frame[] = [[
  [0,0,1,1,1,1,0,0],
  [0,0,1,2,2,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,1,1,1],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,3,3,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,0,0,1,0,0],
  [0,0,1,0,0,1,0,0],
  [0,1,1,0,0,1,1,0],
  [0,0,0,0,0,0,0,0],
]]

// --- Guard frames (same structure, hat on top row) ---
const G_STAND: Frame[] = [[
  [0,3,3,3,3,3,3,0],
  [0,0,1,2,2,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,1,1,1,1,1,1,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,3,3,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,0,0,1,0,0],
  [0,0,1,0,0,1,0,0],
  [0,1,1,0,0,1,1,0],
  [0,0,0,0,0,0,0,0],
]]

const G_RUN: Frame[] = [
  [ // stride right — hat/head/neck lean right
    [0,0,3,3,3,3,3,0],
    [0,0,0,1,2,2,1,0],
    [0,0,0,0,1,1,0,0],
    [0,0,1,1,1,1,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,0,1,0,0],
    [0,0,1,0,0,0,1,0],
    [0,1,1,0,0,0,1,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // legs together — centered
    [0,3,3,3,3,3,3,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,1,1,1,1,1,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [ // stride left — hat/head/neck lean left
    [0,3,3,3,3,3,0,0],
    [0,1,2,2,1,0,0,0],
    [0,0,1,1,0,0,0,0],
    [0,1,1,1,1,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,0,1,0],
    [0,1,0,0,0,1,0,0],
    [0,1,0,0,1,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const G_CLIMB: Frame[] = [
  [
    [0,3,3,3,3,3,3,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,1,0,0],
    [0,0,1,1,1,0,1,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,1,0,0,0],
    [0,0,0,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [
    [0,3,3,3,3,3,3,0],
    [0,0,1,2,2,1,0,0],
    [0,0,1,1,0,0,0,0],
    [0,1,0,1,1,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,0,1,0,0],
    [0,0,1,0,0,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const G_HANG: Frame[] = [
  [
    [0,3,3,3,3,3,3,0],
    [0,0,1,1,1,1,1,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0],
  ],
  [
    [0,3,3,3,3,3,3,0],
    [0,1,1,1,1,1,0,0],
    [0,0,1,2,2,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,3,3,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,1,0,0,1,0,0],
    [0,0,0,1,1,0,0,0],
    [0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0],
  ],
]

const G_FALL: Frame[] = [[
  [0,1,0,0,0,0,1,0],
  [0,0,1,0,0,1,0,0],
  [0,3,1,1,1,1,3,0],
  [0,0,1,2,2,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,1,3,3,1,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,1,1,0,0,0],
  [0,0,0,0,0,0,0,0],
]]

const PLAYER_SPRITES: Record<AnimState, Frame[]> = {
  standing: P_STAND, running: P_RUN, climbing: P_CLIMB,
  hanging: P_HANG, falling: P_FALL, digging: P_DIG,
}
const GUARD_SPRITES: Record<AnimState, Frame[]> = {
  standing: G_STAND, running: G_RUN, climbing: G_CLIMB,
  hanging: G_HANG, falling: G_FALL, digging: G_STAND,
}

/** Render a pixel-art sprite frame centered at (x, y) */
function drawSprite(
  ctx: CanvasRenderingContext2D,
  frame: Frame, x: number, y: number,
  colors: string[], facingLeft: boolean,
): void {
  const rows = frame.length
  const cols = frame[0].length
  const px = 2 // pixel scale
  const w = cols * px
  const h = rows * px
  const sx = Math.floor(x - w / 2)
  let sy = Math.floor(y - h / 2)
  sy += 1 // A9: shift all sprites down 1px so feet touch ground
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const val = frame[r][facingLeft ? (cols - 1 - c) : c]
      if (val === 0) continue
      ctx.fillStyle = colors[val - 1]
      ctx.fillRect(sx + c * px, sy + r * px, px, px)
    }
  }
}

/** Get the current animation frame cycling at ~0.18s intervals */
function getAnimFrame(frames: Frame[], animTime: number, moving: boolean = true): Frame {
  if (!moving) return frames[0]
  const idx = Math.floor(animTime / 0.18) % frames.length
  return frames[idx]
}

function drawPlayer(ctx: CanvasRenderingContext2D, p: Player, animTime: number): void {
  if (!p.alive) return
  const frames = PLAYER_SPRITES[p.animState] || P_STAND
  const frame = getAnimFrame(frames, animTime, p.moving)
  const drawY = p.animState === 'hanging' ? p.y + 8 : p.y
  drawSprite(ctx, frame, p.x, drawY, PLAYER_COLORS, p.facingLeft)
}

function drawGuard(ctx: CanvasRenderingContext2D, g: Guard, animTime: number): void {
  if (g.state === 'dead') return
  ctx.save()
  if (g.state === 'trapped') {
    ctx.globalAlpha = 0.5 + 0.3 * Math.sin(animTime * 8)
  }
  const frames = GUARD_SPRITES[g.animState] || G_STAND
  const frame = getAnimFrame(frames, animTime, g.moving)
  const drawY = g.animState === 'hanging' ? g.y + 8 : g.y
  drawSprite(ctx, frame, g.x, drawY, GUARD_COLORS, g.facingLeft)
  // Gold indicator
  if (g.carriesGold) {
    ctx.globalAlpha = 1
    ctx.fillStyle = C_GOLD
    ctx.beginPath()
    ctx.arc(g.x, g.y + CELL / 2, 3, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()
}

function drawHUD(ctx: CanvasRenderingContext2D, gs: GameState): void {
  ctx.fillStyle = C_HUD
  ctx.font = 'bold 11px monospace'
  ctx.textBaseline = 'top'

  // Score
  ctx.textAlign = 'left'
  ctx.fillText(`SCORE ${gs.score}`, 4, 2)

  // Level
  ctx.textAlign = 'center'
  ctx.fillText(`LVL ${gs.level}`, GAME_WIDTH / 2, 2)

  // Gold remaining
  ctx.textAlign = 'right'
  ctx.fillStyle = C_GOLD
  ctx.fillText(`${'*'.repeat(Math.min(gs.goldRemaining, 10))}`, GAME_WIDTH - 40, 2)

  // Lives
  ctx.fillStyle = C_PLAYER_HUD
  ctx.fillText(`${'@'.repeat(gs.lives)}`, GAME_WIDTH - 4, 2)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const emptyInput: Input = {
  left: false, right: false, up: false, down: false,
  digLeft: false, digRight: false,
}

export default function LodeRunner() {
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('lode-runner') ?? 0
  const { load: loadSaved, save: saveState, clear: clearSaved } = useGameState<GameState>('lode-runner')

  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [level, setLevel] = useState(1)
  const [lives, setLives] = useState(3)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)

  const gsRef = useRef<GameState>(loadLevel(1))
  const gameStatusRef = useRef<GameStatus>('idle')
  const animFrameRef = useRef(0)
  const lastTimeRef = useRef(0)

  // Input tracking
  const keysRef = useRef<Set<string>>(new Set())
  // Track single-press dig actions (consumed once per press)
  const digLeftPressedRef = useRef(false)
  const digRightPressedRef = useRef(false)
  // Mobile d-pad input
  const mobileInputRef = useRef<Input>({ ...emptyInput })

  // -------------------------------------------------------------------------
  // Draw
  // -------------------------------------------------------------------------

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scale = scaleRef.current
    canvas.width = Math.floor(GAME_WIDTH * scale)
    canvas.height = Math.floor(GAME_HEIGHT * scale)

    ctx.save()
    ctx.scale(scale, scale)

    const gs = gsRef.current

    drawBackground(ctx)
    drawTiles(ctx, gs)
    drawGold(ctx, gs)

    // Draw guards
    for (const g of gs.guards) {
      drawGuard(ctx, g, gs.animTime)
    }

    // Draw player
    drawPlayer(ctx, gs.player, gs.animTime)

    // Draw dig projectiles (A11)
    for (const dp of gs.digProjectiles) {
      const alpha = dp.timer / 0.25
      ctx.save()
      ctx.globalAlpha = alpha
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2
      // Line from player hand down to target brick
      const px = gs.player.x + (dp.fromLeft ? -6 : 6)
      const py = gs.player.y + 4
      const tx = dp.col * CELL + CELL / 2
      const ty = dp.row * CELL
      ctx.beginPath()
      ctx.moveTo(px, py)
      ctx.lineTo(tx, ty)
      ctx.stroke()
      ctx.restore()
    }

    // HUD
    drawHUD(ctx, gs)

    ctx.restore()
  }, [])

  // -------------------------------------------------------------------------
  // Game loop
  // -------------------------------------------------------------------------

  const tick = useCallback((timestamp: number) => {
    if (gameStatusRef.current !== 'playing') return

    const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.05)
    lastTimeRef.current = timestamp

    // Build input from keyboard + mobile
    const keys = keysRef.current
    const mobile = mobileInputRef.current
    const input: Input = {
      left: keys.has('ArrowLeft') || keys.has('a') || keys.has('A') || mobile.left,
      right: keys.has('ArrowRight') || keys.has('d') || keys.has('D') || mobile.right,
      up: keys.has('ArrowUp') || keys.has('w') || keys.has('W') || mobile.up,
      down: keys.has('ArrowDown') || keys.has('s') || keys.has('S') || mobile.down,
      digLeft: digLeftPressedRef.current || mobile.digLeft,
      digRight: digRightPressedRef.current || mobile.digRight,
    }
    // Consume dig presses (keyboard only — mobile is held)
    digLeftPressedRef.current = false
    digRightPressedRef.current = false

    const gs = updateGame(gsRef.current, dt, input)
    gsRef.current = gs

    // Sync React state
    setScore(gs.score)
    setLevel(gs.level)
    setLives(gs.lives)

    // Check game over
    if (gs.gameOver) {
      gameStatusRef.current = 'lost'
      setGameStatus('lost')
      saveScore('lode-runner', gs.score)
      clearSaved()
      draw()
      return
    }

    // Check level complete
    if (gs.levelComplete) {
      const next = nextLevel(gs)
      gsRef.current = next
      if (next.won) {
        gameStatusRef.current = 'won'
        setGameStatus('won')
        saveScore('lode-runner', next.score)
        clearSaved()
        draw()
        return
      }
      setLevel(next.level)
    }

    // Auto-save game state
    saveState(gs)

    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, saveScore, saveState, clearSaved])

  // -------------------------------------------------------------------------
  // Start / restart
  // -------------------------------------------------------------------------

  const startGame = useCallback(() => {
    clearSaved()
    gsRef.current = loadLevel(1)
    setScore(0)
    setLevel(1)
    setLives(3)
    keysRef.current.clear()
    digLeftPressedRef.current = false
    digRightPressedRef.current = false
    mobileInputRef.current = { ...emptyInput }

    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    lastTimeRef.current = performance.now()
    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, tick, clearSaved])

  // -------------------------------------------------------------------------
  // Keyboard controls
  // -------------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const gameKeys = [
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
        'w', 'a', 's', 'd', 'W', 'A', 'S', 'D',
        'q', 'Q', 'z', 'Z', 'e', 'E', 'x', 'X',
      ]
      if (gameKeys.includes(e.key)) {
        e.preventDefault()
        keysRef.current.add(e.key)
      }

      // Dig actions — single press
      if ((e.key === 'q' || e.key === 'Q' || e.key === 'z' || e.key === 'Z') && !e.repeat) {
        digLeftPressedRef.current = true
      }
      if ((e.key === 'e' || e.key === 'E' || e.key === 'x' || e.key === 'X') && !e.repeat) {
        digRightPressedRef.current = true
      }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      keysRef.current.delete(e.key)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [])

  // -------------------------------------------------------------------------
  // Responsive scaling
  // -------------------------------------------------------------------------

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const updateScale = () => {
      const w = container.clientWidth
      const availableHeight = window.innerHeight - 320
      scaleRef.current = Math.min(1, w / GAME_WIDTH, availableHeight / GAME_HEIGHT)
      draw()
    }
    updateScale()
    const observer = new ResizeObserver(updateScale)
    observer.observe(container)
    return () => observer.disconnect()
  }, [draw])

  // Load saved state on mount
  useEffect(() => {
    const saved = loadSaved()
    if (saved && !saved.gameOver && !saved.won) {
      gsRef.current = saved
      setScore(saved.score)
      setLevel(saved.level)
      setLives(saved.lives)
      gameStatusRef.current = 'playing'
      setGameStatus('playing')
      lastTimeRef.current = performance.now()
      draw()
      animFrameRef.current = requestAnimationFrame(tick)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Initial draw
  useEffect(() => { draw() }, [draw])

  // Cleanup — save state and cancel animation
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animFrameRef.current)
      if (gameStatusRef.current === 'playing') {
        saveState(gsRef.current)
      }
    }
  }, [saveState])

  // -------------------------------------------------------------------------
  // Mobile d-pad helpers
  // -------------------------------------------------------------------------

  const setMobileKey = useCallback((key: keyof Input, active: boolean) => {
    mobileInputRef.current = { ...mobileInputRef.current, [key]: active }
  }, [])

  const dpadBtn = (label: string, key: keyof Input, extraClass: string = '') => (
    <button
      className={`w-12 h-12 rounded-lg bg-slate-700/80 active:bg-slate-600
        text-slate-300 font-bold text-lg select-none touch-none ${extraClass}`}
      onPointerDown={(e) => { e.preventDefault(); setMobileKey(key, true) }}
      onPointerUp={() => setMobileKey(key, false)}
      onPointerLeave={() => setMobileKey(key, false)}
      onPointerCancel={() => setMobileKey(key, false)}
    >
      {label}
    </button>
  )

  // -------------------------------------------------------------------------
  // Controls bar
  // -------------------------------------------------------------------------

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        <span className="text-xs text-slate-400">Lives:</span>
        <div className="flex space-x-1">
          {Array.from({ length: lives }).map((_, i) => (
            <span key={i} className="text-yellow-500 text-sm font-bold">@</span>
          ))}
        </div>
      </div>
      <span className="text-xs text-slate-400">
        Lvl {level}: {LEVEL_NAMES[level - 1] ?? ''}
      </span>
      <button
        onClick={startGame}
        className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300
                   hover:bg-slate-600 transition-colors"
      >
        New Game
      </button>
    </div>
  )

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <GameLayout title="Lode Runner" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-3" ref={containerRef}>
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 max-w-full"
          style={{ touchAction: 'none' }}
        />

        {/* Mobile d-pad — visible on small screens */}
        {gameStatus === 'playing' && (
          <div className="flex sm:hidden items-center justify-between w-full max-w-xs px-2">
            {/* Dig left */}
            <div className="flex flex-col items-center space-y-1">
              {dpadBtn('DL', 'digLeft', 'w-11 h-11 text-sm bg-amber-800/60 active:bg-amber-700')}
              <span className="text-[10px] text-slate-500">Dig L</span>
            </div>

            {/* D-pad cross */}
            <div className="flex flex-col items-center">
              <div className="flex justify-center">
                {dpadBtn('\u25B2', 'up')}
              </div>
              <div className="flex space-x-1">
                {dpadBtn('\u25C0', 'left')}
                <div className="w-12 h-12" /> {/* spacer */}
                {dpadBtn('\u25B6', 'right')}
              </div>
              <div className="flex justify-center">
                {dpadBtn('\u25BC', 'down')}
              </div>
            </div>

            {/* Dig right */}
            <div className="flex flex-col items-center space-y-1">
              {dpadBtn('DR', 'digRight', 'w-11 h-11 text-sm bg-amber-800/60 active:bg-amber-700')}
              <span className="text-[10px] text-slate-500">Dig R</span>
            </div>
          </div>
        )}

        {/* Idle overlay */}
        {gameStatus === 'idle' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <div className="text-center">
              <button
                onClick={startGame}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white
                           rounded-lg font-semibold transition-colors"
              >
                Start Game
              </button>
              <p className="text-xs text-slate-400 mt-3">
                Collect all gold, then escape at the top!
              </p>
            </div>
          </div>
        )}

        {/* Game over */}
        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            message={`Reached level ${level}: ${LEVEL_NAMES[level - 1] ?? ''}`}
            onPlayAgain={startGame}
          />
        )}

        {/* Victory */}
        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={score}
            bestScore={bestScore}
            message="All 10 levels completed!"
            onPlayAgain={startGame}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys / WASD to move. Q/Z dig left. E/X dig right.
        </p>
      </div>
    </GameLayout>
  )
}
