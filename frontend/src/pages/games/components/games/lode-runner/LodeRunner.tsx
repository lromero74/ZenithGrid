/**
 * Lode Runner — canvas-based puzzle-platformer.
 *
 * Features: keyboard + mobile d-pad controls, 150 classic levels,
 * gold collection, brick digging, guard AI, responsive scaling.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  loadLevel, updateGame, nextLevel,
  GAME_WIDTH, GAME_HEIGHT, CELL, COLS, ROWS, TOTAL_LEVELS,
  Tile, BRICK_FILL_TIME,
  type AnimState, type GameState, type Input, type Player, type Guard,
} from './lodeRunnerEngine'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'
import { HelpCircle, X } from 'lucide-react'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

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
// Help modal
// ---------------------------------------------------------------------------

function LodeRunnerHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Lode Runner</h2>

        <Sec title="Goal">
          Collect all the gold on each level, then climb to the top of the screen to escape.
          A hidden ladder appears once all gold is collected. Complete all {TOTAL_LEVELS} levels to win!
        </Sec>

        <Sec title="Movement">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Arrow keys</B> or <B>WASD</B> to move left, right, up, and down.</Li>
            <Li>Climb <B>ladders</B> to move vertically (up/down).</Li>
            <Li>Traverse <B>bars</B> (horizontal rails) by moving left/right while hanging.</Li>
            <Li>Press <B>down</B> while on a bar to drop off and fall.</Li>
            <Li>You cannot walk through <B>bricks</B> or <B>solid blocks</B>.</Li>
            <Li>You will <B>fall</B> if there is nothing beneath you (no ground, ladder, or bar).</Li>
          </ul>
        </Sec>

        <Sec title="Digging">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Q</B> or <B>Z</B> to dig the brick below-left. <B>E</B> or <B>X</B> to dig below-right.</Li>
            <Li>You can only dig <B>bricks</B> — solid blocks and empty space cannot be dug.</Li>
            <Li>Dug holes stay open for <B>5 seconds</B>, then fill back in over 1.5 seconds.</Li>
            <Li>There is a short <B>cooldown</B> between digs (0.4 seconds).</Li>
            <Li>Use digging to create paths through brick floors or to <B>trap guards</B>.</Li>
            <Li>If you are standing inside a brick when it refills, you <B>die</B>.</Li>
          </ul>
        </Sec>

        <Sec title="Gold & Escape">
          <ul className="space-y-1 text-slate-300">
            <Li>Collect all <B>gold nuggets</B> on the level (<B>250 points</B> each).</Li>
            <Li>Once all gold is collected, <B>hidden ladders</B> appear (flashing green).</Li>
            <Li>Reach the <B>top of the screen</B> (row 0) to complete the level (<B>500 points</B>).</Li>
            <Li>Guards can also <B>pick up gold</B> — trap them to make them drop it.</Li>
          </ul>
        </Sec>

        <Sec title="Guards">
          <ul className="space-y-1 text-slate-300">
            <Li>Red guards <B>chase you</B> using pathfinding (BFS). They climb ladders, traverse bars, and fall.</Li>
            <Li>Contact with a guard <B>kills you</B> (unless you have post-respawn invincibility).</Li>
            <Li>Guards can be <B>trapped</B> by digging a hole and letting them fall in.</Li>
            <Li>Trapped guards try to <B>climb out</B> after a few seconds.</Li>
            <Li>If a brick refills while a guard is trapped, the guard <B>dies</B> and respawns at the top
              of the level after 3 seconds (<B>75 points</B>).</Li>
            <Li>Guards carrying gold <B>drop it</B> above the hole when trapped.</Li>
            <Li>You can stand on top of a <B>trapped guard</B> as a platform.</Li>
          </ul>
        </Sec>

        <Sec title="Trap Bricks">
          <ul className="space-y-1 text-slate-300">
            <Li>Some bricks are <B>traps</B> — they look identical to normal bricks but are passable.</Li>
            <Li>Both you and guards will <B>fall through</B> trap bricks.</Li>
          </ul>
        </Sec>

        <Sec title="Lives & Scoring">
          <ul className="space-y-1 text-slate-300">
            <Li>You start with <B>3 lives</B>. Losing all lives ends the game.</Li>
            <Li>After dying, you respawn with brief <B>invincibility</B> (blinking sprite, 2 seconds).</Li>
            <Li><B>250 pts</B> per gold collected, <B>75 pts</B> per guard killed,
              <B> 500 pts</B> for completing a level.</Li>
          </ul>
        </Sec>

        <Sec title="Controls (Desktop)">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Arrow keys</B> or <B>WASD</B> — move left / right / up / down.</Li>
            <Li><B>Q / Z</B> — dig left (brick below and to your left).</Li>
            <Li><B>E / X</B> — dig right (brick below and to your right).</Li>
          </ul>
        </Sec>

        <Sec title="Controls (Mobile)">
          <ul className="space-y-1 text-slate-300">
            <Li>Use the on-screen <B>d-pad</B> for movement.</Li>
            <Li>Tap <B>DL</B> to dig left, <B>DR</B> to dig right.</Li>
          </ul>
        </Sec>

        <Sec title="Tips">
          <ul className="space-y-1 text-slate-300">
            <Li>Plan your route before grabbing gold — some paths become one-way once bricks refill.</Li>
            <Li>Dig holes to trap guards and create safe passages through brick platforms.</Li>
            <Li>You can run across the top of a hole before it fills, but don&apos;t linger!</Li>
            <Li>Guards will chase you intelligently — use ladders and bars to outmaneuver them.</Li>
            <Li>Your game is <B>auto-saved</B> — you can resume where you left off.</Li>
          </ul>
        </Sec>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-slate-700 text-slate-300 text-xs hover:bg-slate-600 transition-colors"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

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
          ctx.moveTo(x, y + 2)
          ctx.lineTo(x + CELL, y + 2)
          ctx.stroke()
          // Grip dots
          ctx.fillStyle = C_BAR
          ctx.beginPath()
          ctx.arc(x + CELL / 2, y + 2, 2, 0, Math.PI * 2)
          ctx.fill()
          break
        case Tile.Trap:
          // Looks identical to brick — player/guards fall through
          drawBrickPattern(ctx, x, y)
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
  return frames[idx] ?? frames[0]
}

function drawPlayer(ctx: CanvasRenderingContext2D, p: Player, animTime: number): void {
  if (!p.alive) return
  // Blink during invincibility (visible 75% of the time)
  if (p.invincible > 0 && Math.floor(animTime * 8) % 4 === 0) return
  const frames = PLAYER_SPRITES[p.animState] || P_STAND
  const frame = getAnimFrame(frames, animTime, p.moving)
  drawSprite(ctx, frame, p.x, p.y, PLAYER_COLORS, p.facingLeft)
}

function drawGuard(ctx: CanvasRenderingContext2D, g: Guard, animTime: number): void {
  if (g.state === 'dead') return
  ctx.save()
  if (g.state === 'trapped') {
    ctx.globalAlpha = 0.5 + 0.3 * Math.sin(animTime * 8)
  }
  const frames = GUARD_SPRITES[g.animState] || G_STAND
  const frame = getAnimFrame(frames, animTime, g.moving)
  drawSprite(ctx, frame, g.x, g.y, GUARD_COLORS, g.facingLeft)
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

function LodeRunnerSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object, intervalMs?: number) => void; isMultiplayer?: boolean } = {}) {
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('lode-runner') ?? 0
  const { load: loadSaved, save: saveState, clear: clearSaved } = useGameState<GameState>('lode-runner')

  // Music
  const song = useMemo(() => getSongForGame('lode-runner'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('lode-runner')

  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [level, setLevel] = useState(1)
  const [lives, setLives] = useState(3)
  const [showHelp, setShowHelp] = useState(false)

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
    // Consume dig presses only when player is aligned and grounded —
    // otherwise the press is lost before the engine can process it
    const pl = gsRef.current.player
    const cx = pl.col * CELL + CELL / 2
    const cy = pl.row * CELL + CELL / 2
    const aligned = Math.abs(pl.x - cx) <= 2 && Math.abs(pl.y - cy) <= 2
    if (aligned && !pl.falling) {
      digLeftPressedRef.current = false
      digRightPressedRef.current = false
    }

    const prevScore = gsRef.current.score
    const prevPlayerAlive = gsRef.current.player.alive
    const gs = updateGame(gsRef.current, dt, input)
    gsRef.current = gs

    // Detect gold collection (score increased)
    if (gs.score > prevScore) {
      sfx.play('collect')
    }

    // Detect dig action
    if (input.digLeft || input.digRight) {
      sfx.play('dig')
    }

    // Detect player death
    if (prevPlayerAlive && !gs.player.alive) {
      sfx.play('die')
    }

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
      onGameEnd?.('loss', gs.level)
      draw()
      return
    }

    // Check level complete
    if (gs.levelComplete) {
      sfx.play('level')
      const next = nextLevel(gs)
      gsRef.current = next
      if (next.won) {
        gameStatusRef.current = 'won'
        setGameStatus('won')
        saveScore('lode-runner', next.score)
        clearSaved()
        onGameEnd?.('win', next.level)
        draw()
        return
      }
      setLevel(next.level)
      onGameEnd?.('win', next.level)
    }

    // Auto-save game state (skip if player is dead — next frame handles respawn)
    if (gs.player.alive) saveState(gs)

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
    music.init()
    sfx.init()
    music.start()
    lastTimeRef.current = performance.now()
    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, tick, clearSaved, music, sfx])

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
    if (saved && !saved.gameOver && !saved.won
        && Array.isArray(saved.grid)
        && Array.isArray(saved.guards)
        && Array.isArray(saved.dugBricks)
        && Array.isArray(saved.digProjectiles)
        && Array.isArray(saved.goldMap)
        && saved.player
        && typeof saved.animTime === 'number'
        && Number.isFinite(saved.animTime)) {
      gsRef.current = saved
      setScore(saved.score)
      setLevel(saved.level)
      setLives(saved.lives)
      gameStatusRef.current = 'playing'
      setGameStatus('playing')
      lastTimeRef.current = performance.now()
      draw()
      animFrameRef.current = requestAnimationFrame(tick)
    } else if (saved) {
      clearSaved()  // discard corrupted/stale state
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
        Lvl {level}/{TOTAL_LEVELS}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <button
          onClick={startGame}
          className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300
                     hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
      </div>
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
        {gameStatus === 'lost' && !isMultiplayer && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            message={`Reached level ${level} of ${TOTAL_LEVELS}`}
            onPlayAgain={startGame}
            music={music}
            sfx={sfx}
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
            music={music}
            sfx={sfx}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys / WASD to move. Q/Z dig left. E/X dig right.
        </p>
      </div>

      {showHelp && <LodeRunnerHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (highest level reached wins) ─────────────────────────

function LodeRunnerRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, throttledBroadcast, reportScore, reportFinish, leaveRoom } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    const lvl = score ?? 1
    reportScore(lvl)
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, lvl)
  }, [reportScore, reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <LodeRunnerSinglePlayer onGameEnd={handleGameEnd} onStateChange={throttledBroadcast} isMultiplayer />
    </div>
  )
}

export default function LodeRunner() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'lode-runner',
        gameName: 'Lode Runner',
        modes: ['best_score'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { best_score: 'Highest level reached wins' },
      }}
      renderSinglePlayer={() => <LodeRunnerSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig, onLeave) =>
        <LodeRunnerRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
      }
    />
  )
}
