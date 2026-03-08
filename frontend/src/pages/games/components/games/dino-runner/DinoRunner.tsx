/**
 * Dino Runner — canvas-based pixel-art endless runner.
 *
 * Features: keyboard + touch controls, variable-height jumps, ducking,
 * day/night cycle, progressive speed, high score tracking.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  createGame, update, computeAutoInput, getDinoSprite, getObstacleSprite, getSpriteSize,
  CANVAS_WIDTH, CANVAS_HEIGHT, PIXEL_SCALE, GROUND_Y, PALETTE,
  CLOUD_SPRITES, BIOMES, INITIAL_SPEED, MAX_SPEED, DINO_X,
  RAIN_CLOUD_SPRITES, STORM_CLOUD_SPRITES, WEATHER_CLOUD_SCALE,
  getWeatherMultiplier, GROUND_LAYER_SPEEDS,
  type GameState, type InputState,
} from './dinoRunnerEngine'
import { Eye, EyeOff, Music } from 'lucide-react'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

/** Interpolate between two hex colors. t in [0,1]. */
function lerpColor(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16)
  const pb = parseInt(b.slice(1), 16)
  const r = Math.round(((pa >> 16) & 0xff) * (1 - t) + ((pb >> 16) & 0xff) * t)
  const g = Math.round(((pa >> 8) & 0xff) * (1 - t) + ((pb >> 8) & 0xff) * t)
  const bl = Math.round((pa & 0xff) * (1 - t) + (pb & 0xff) * t)
  return `#${((r << 16) | (g << 8) | bl).toString(16).padStart(6, '0')}`
}

/** Desaturate a hex color. amount 0 = full color, 1 = grayscale. */
function desaturateHex(hex: string, amount: number): string {
  if (amount <= 0) return hex
  const v = parseInt(hex.slice(1), 16)
  const r = (v >> 16) & 0xff
  const g = (v >> 8) & 0xff
  const b = v & 0xff
  const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b)
  const nr = Math.round(r + (gray - r) * amount)
  const ng = Math.round(g + (gray - g) * amount)
  const nb = Math.round(b + (gray - b) * amount)
  return `#${((nr << 16) | (ng << 8) | nb).toString(16).padStart(6, '0')}`
}

/** Build a desaturated palette for the current frame. */
function buildFramePalette(desat: number): Record<number, string> {
  if (desat <= 0) return PALETTE
  const p: Record<number, string> = {}
  for (const key in PALETTE) {
    const k = Number(key)
    p[k] = k === 0 ? 'transparent' : desaturateHex(PALETTE[k], desat)
  }
  return p
}

/**
 * Multi-stop sky gradient: blue day → golden sunset → red dusk → dark night.
 * nt goes 0 (day) → 1 (night). Sunset happens in the 0.15–0.45 range.
 */
const SKY_STOPS: [number, string][] = [
  [0.00, '#87ceeb'], // clear blue day
  [0.15, '#87ceeb'], // still blue
  [0.25, '#f0a050'], // golden sunset
  [0.35, '#d04030'], // red dusk
  [0.50, '#2a1535'], // deep purple twilight
  [1.00, '#0a0a1e'], // dark night
]

function getSkyColor(nt: number): string {
  if (nt <= SKY_STOPS[0][0]) return SKY_STOPS[0][1]
  for (let i = 1; i < SKY_STOPS.length; i++) {
    if (nt <= SKY_STOPS[i][0]) {
      const t = (nt - SKY_STOPS[i - 1][0]) / (SKY_STOPS[i][0] - SKY_STOPS[i - 1][0])
      return lerpColor(SKY_STOPS[i - 1][1], SKY_STOPS[i][1], t)
    }
  }
  return SKY_STOPS[SKY_STOPS.length - 1][1]
}

/**
 * Cloud tint: white during day, warm orange/pink during sunset, dim gray at night.
 */
const CLOUD_TINT_STOPS: [number, string][] = [
  [0.00, '#ffffff'], // white
  [0.15, '#ffffff'], // still white
  [0.22, '#ffe0a0'], // warm golden
  [0.30, '#ff9070'], // orange-pink
  [0.40, '#cc5050'], // red-tinted
  [0.55, '#444466'], // muted dusk
  [1.00, '#222233'], // dark night
]

function getCloudTint(nt: number): string {
  if (nt <= CLOUD_TINT_STOPS[0][0]) return CLOUD_TINT_STOPS[0][1]
  for (let i = 1; i < CLOUD_TINT_STOPS.length; i++) {
    if (nt <= CLOUD_TINT_STOPS[i][0]) {
      const t = (nt - CLOUD_TINT_STOPS[i - 1][0]) / (CLOUD_TINT_STOPS[i][0] - CLOUD_TINT_STOPS[i - 1][0])
      return lerpColor(CLOUD_TINT_STOPS[i - 1][1], CLOUD_TINT_STOPS[i][1], t)
    }
  }
  return CLOUD_TINT_STOPS[CLOUD_TINT_STOPS.length - 1][1]
}

/** Draw a parallax terrain layer as a filled silhouette. */
function drawParallaxLayer(
  ctx: CanvasRenderingContext2D,
  heights: number[],
  offset: number,
  step: number,
  color: string,
): void {
  ctx.fillStyle = color
  const len = heights.length
  for (let sx = 0; sx < CANVAS_WIDTH; sx += step) {
    const idx = ((Math.floor((offset + sx) / step) % len) + len) % len
    const h = heights[idx]
    if (h > 0) {
      ctx.fillRect(sx, GROUND_Y - h, step, h + PIXEL_SCALE)
    }
  }
}

/**
 * Camera offset: as speed increases, dino shifts left so the player
 * sees further ahead. Returns the X offset to subtract from dino position.
 */
function getCameraShift(speed: number): number {
  const t = Math.max(0, (speed - INITIAL_SPEED) / (MAX_SPEED - INITIAL_SPEED))
  return t * 20 // up to 20px shift at max speed
}

/** Draw a sprite (2D number array) at (x, y) using a color palette. */
function drawSprite(
  ctx: CanvasRenderingContext2D,
  sprite: number[][],
  x: number,
  y: number,
  scale: number = PIXEL_SCALE,
  palette: Record<number, string> = PALETTE,
): void {
  // Snap sprite origin to integer to avoid sub-pixel seams between pixels
  const sx = Math.round(x)
  const sy = Math.round(y)
  const ps = Math.round(scale) || 1
  for (let row = 0; row < sprite.length; row++) {
    for (let col = 0; col < sprite[row].length; col++) {
      const color = sprite[row][col]
      if (color === 0) continue
      ctx.fillStyle = palette[color] || '#ff00ff'
      ctx.fillRect(sx + col * ps, sy + row * ps, ps, ps)
    }
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DinoRunner() {
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [displayScore, setDisplayScore] = useState(0)
  const [displayHigh, setDisplayHigh] = useState(0)
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('dino-runner') ?? 0

  const [rhythmMode, setRhythmMode] = useState(false)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<GameState>(createGame(bestScore))
  const inputRef = useRef<InputState>({ jump: false, duck: false })
  const rafRef = useRef<number>(0)
  const gameStatusRef = useRef<GameStatus>('idle')
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const autoPlayRef = useRef(false)
  const [autoPlay, setAutoPlay] = useState(false)

  // Music engine
  const dinoSong = useMemo(() => getSongForGame('dino-runner'), [])
  const music = useGameMusic(dinoSong)
  const sfx = useGameSFX('dino-runner')

  // -----------------------------------------------------------------------
  // Landscape fullscreen on mobile
  // -----------------------------------------------------------------------

  const [isLandscape, setIsLandscape] = useState(false)

  useEffect(() => {
    const mql = window.matchMedia('(orientation: landscape) and (max-height: 500px)')
    const update = () => setIsLandscape(mql.matches)
    update()
    mql.addEventListener('change', update)
    return () => mql.removeEventListener('change', update)
  }, [])

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  const render = useCallback((state: GameState) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { nightTransition: nt, weather } = state

    // --- Night desaturation (scotopic vision) ---
    // Meteors and lightning temporarily restore color
    const baseDesat = nt * 0.7
    let flashReduction = 0
    if (weather.type === 'meteor-shower' && weather.particles.length > 0) {
      flashReduction = weather.intensity * 0.5
    }
    if (weather.lightning > 0) {
      flashReduction = Math.max(flashReduction, weather.lightning / 18)
    }
    const desat = Math.max(0, baseDesat - flashReduction)
    const framePalette = buildFramePalette(desat)

    // --- Background (multi-stop sky: blue → sunset → night, tinted by weather) ---
    let skyColor = getSkyColor(nt)
    // Weather tints the sky appropriately
    if (weather.type !== 'none' && weather.intensity > 0) {
      const wi = weather.intensity
      if (weather.type === 'rain') {
        skyColor = lerpColor(skyColor, lerpColor('#8899aa', '#3a3a50', nt), wi * 0.35)
      } else if (weather.type === 'thunderstorm') {
        skyColor = lerpColor(skyColor, lerpColor('#4a4a5a', '#1a1a28', nt), wi * 0.5)
      } else if (weather.type === 'sandstorm') {
        skyColor = lerpColor(skyColor, lerpColor('#c8a860', '#5a4020', nt), wi * 0.4)
      } else if (weather.type === 'snowstorm') {
        skyColor = lerpColor(skyColor, lerpColor('#b0c0d0', '#404858', nt), wi * 0.3)
      }
    }
    ctx.fillStyle = desaturateHex(skyColor, desat * 0.3)
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

    // --- Stars (fade in after dusk, nt > 0.4, varying sizes) ---
    if (nt > 0.4) {
      const starAlpha = Math.min(1, (nt - 0.4) / 0.3)
      ctx.fillStyle = '#ffffff'
      for (const star of state.stars) {
        if (star.x < -2 || star.x > CANVAS_WIDTH + 2 || star.y < -2 || star.y > GROUND_Y - 38) continue
        ctx.globalAlpha = starAlpha * (star.size > 1 ? 1 : 0.6)
        ctx.fillRect(star.x, star.y, star.size, star.size)
      }
      ctx.globalAlpha = 1
    }

    // --- Parallax landscape ---
    const { parallax } = state
    const biome = BIOMES[parallax.biomeIndex]
    const prevBiome = BIOMES[parallax.prevBiomeIndex]
    const bt = parallax.transitionProgress
    const desatSky = desaturateHex(skyColor, desat * 0.3)
    // Atmospheric perspective: far=40% sky blend, mid=15%, near=0%
    const atmosBlend: Record<string, number> = { far: 0.4, mid: 0.15, near: 0 }
    const layerColor = (b: typeof biome, layer: 'far' | 'mid' | 'near') => {
      const col = desaturateHex(lerpColor(b[layer].dayColor, b[layer].nightColor, nt), desat)
      return lerpColor(col, desatSky, atmosBlend[layer])
    }

    // Biome-aware color lerp: blends prev/current biome colors with night & desaturation
    const bLerp = (dayA: string, nightA: string, dayB: string, nightB: string) => {
      const a = lerpColor(dayA, nightA, nt)
      const b = lerpColor(dayB, nightB, nt)
      return desaturateHex(bt < 1 ? lerpColor(a, b, bt) : b, desat)
    }

    // Build biome-aware obstacle palette (override indices 6 & 7 per biome)
    const obsPalette: Record<number, string> = {
      ...framePalette,
      6: bLerp(prevBiome.obsOutlineDay, prevBiome.obsOutlineNight, biome.obsOutlineDay, biome.obsOutlineNight),
      7: bLerp(prevBiome.obsFillDay, prevBiome.obsFillNight, biome.obsFillDay, biome.obsFillNight),
    }

    // Far layer — draw both biomes during transition for crossfade
    if (bt < 1) {
      ctx.globalAlpha = 1 - bt
      drawParallaxLayer(ctx, prevBiome.far.heights, parallax.farOffset, prevBiome.far.step, layerColor(prevBiome, 'far'))
      ctx.globalAlpha = 1
    }
    ctx.globalAlpha = bt < 1 ? bt : 1
    drawParallaxLayer(ctx, biome.far.heights, parallax.farOffset, biome.far.step, layerColor(biome, 'far'))
    ctx.globalAlpha = 1

    // --- Weather clouds (pixel art) ---
    if ((weather.type === 'rain' || weather.type === 'thunderstorm' || weather.type === 'snowstorm')
      && weather.stormClouds.length > 0) {
      const cloudAlpha = weather.intensity * (weather.type === 'rain' ? 0.45 : 0.6)
      const isStorm = weather.type === 'thunderstorm' || weather.type === 'snowstorm'
      const sprites = isStorm ? STORM_CLOUD_SPRITES : RAIN_CLOUD_SPRITES
      // Build pixel-art cloud palette: rain=2-tone(1,2), storm=3-tone(1,2,3)
      let cloudPalette: Record<number, string>
      if (weather.type === 'rain') {
        cloudPalette = {
          0: 'transparent',
          1: lerpColor('#9098a8', '#384050', nt),
          2: lerpColor('#687080', '#283040', nt),
        }
      } else if (weather.type === 'snowstorm') {
        cloudPalette = {
          0: 'transparent',
          1: lerpColor('#8890a0', '#303848', nt),
          2: lerpColor('#687080', '#202030', nt),
          3: lerpColor('#485060', '#101020', nt),
        }
      } else {
        // thunderstorm — dark and menacing
        cloudPalette = {
          0: 'transparent',
          1: lerpColor('#606878', '#282838', nt),
          2: lerpColor('#3e4450', '#181828', nt),
          3: lerpColor('#252830', '#0c0c18', nt),
        }
      }
      ctx.globalAlpha = cloudAlpha
      for (const sc of weather.stormClouds) {
        const sprite = sprites[sc.spriteIndex % sprites.length]
        // Derive scale from stored width (supports multi-layer sizing)
        const scScale = sprite[0].length > 0 ? Math.round(sc.w / sprite[0].length) : WEATHER_CLOUD_SCALE
        drawSprite(ctx, sprite, sc.x, sc.y, scScale, cloudPalette)
      }
      ctx.globalAlpha = 1
    }

    // --- Clouds (tinted by time of day: white → sunset gold/pink → dim night) ---
    const cloudTint = getCloudTint(nt)
    const cloudPaletteDay: Record<number, string> = { ...framePalette, 4: cloudTint }
    ctx.globalAlpha = 1
    for (const cloud of state.clouds) {
      drawSprite(ctx, CLOUD_SPRITES[cloud.spriteIndex % CLOUD_SPRITES.length], cloud.x, cloud.y, cloud.scale, cloudPaletteDay)
    }

    // Mid + near layers (in front of clouds) — crossfade during transition
    if (bt < 1) {
      ctx.globalAlpha = 1 - bt
      drawParallaxLayer(ctx, prevBiome.mid.heights, parallax.midOffset, prevBiome.mid.step, layerColor(prevBiome, 'mid'))
      drawParallaxLayer(ctx, prevBiome.near.heights, parallax.nearOffset, prevBiome.near.step, layerColor(prevBiome, 'near'))
      ctx.globalAlpha = bt
    }
    drawParallaxLayer(ctx, biome.mid.heights, parallax.midOffset, biome.mid.step, layerColor(biome, 'mid'))
    drawParallaxLayer(ctx, biome.near.heights, parallax.nearOffset, biome.near.step, layerColor(biome, 'near'))
    ctx.globalAlpha = 1

    // --- Camera shift (dino moves left at higher speeds, showing more ahead) ---
    const camShift = getCameraShift(state.speed)

    // --- Ground (biome-colored with crossfade) ---
    const groundColor = bLerp(prevBiome.groundDay, prevBiome.groundNight, biome.groundDay, biome.groundNight)
    const groundHighlight = bLerp(prevBiome.accentDay, prevBiome.accentNight, biome.accentDay, biome.accentNight)
    ctx.fillStyle = groundColor
    ctx.fillRect(0, GROUND_Y + PIXEL_SCALE, CANVAS_WIDTH, CANVAS_HEIGHT - GROUND_Y)

    // Ground texture — sparse static bumps (most texture now via parallax particles)
    ctx.fillStyle = groundHighlight
    for (let x = -state.ground.offset; x < CANVAS_WIDTH; x += 24) {
      ctx.fillRect(x, GROUND_Y + PIXEL_SCALE, 3, 2)
    }

    // Dirt particles — 3 parallax layers with bright specks
    const dirtColors = GROUND_LAYER_SPEEDS.map((_, i) =>
      lerpColor(groundColor, groundHighlight, 0.4 - i * 0.12)
    )
    const brightColor = lerpColor(groundHighlight, '#ffffff', 0.5)
    for (const p of state.ground.particles) {
      if (p.x < 0 || p.x > CANVAS_WIDTH) continue
      ctx.fillStyle = p.bright ? brightColor : dirtColors[p.layer]
      ctx.fillRect(Math.floor(p.x), GROUND_Y + PIXEL_SCALE + p.y, p.size, p.size)
    }

    // Ground line
    const lineColor = bLerp(prevBiome.lineDay, prevBiome.lineNight, biome.lineDay, biome.lineNight)
    ctx.fillStyle = lineColor
    ctx.fillRect(0, GROUND_Y + PIXEL_SCALE - 1, CANVAS_WIDTH, 1)

    // --- Obstacles (shifted by camera, biome-colored) ---
    for (const obs of state.obstacles) {
      const sprite = getObstacleSprite(obs)
      const size = getSpriteSize(sprite)
      drawSprite(ctx, sprite, obs.x - camShift, obs.y - size.h * PIXEL_SCALE, PIXEL_SCALE,
        obs.type === 'pterodactyl' ? framePalette : obsPalette)
    }

    // --- Dino (shifted by camera, pushed by wind) ---
    const dinoSprite = getDinoSprite(state.dino)
    const dinoSize = getSpriteSize(dinoSprite)
    const dinoDrawX = DINO_X - camShift
    const dinoDrawY = state.dino.y - dinoSize.h * PIXEL_SCALE + PIXEL_SCALE
    const windPush = weather.windStrength * weather.intensity
    if (windPush > 0.05) {
      // Wind lean: render dino to an offscreen canvas first, then drawImage
      // with rotation + imageSmoothingEnabled=false to avoid anti-aliased
      // pixel edges that make the sprite look semi-transparent.
      const lean = windPush * 0.08 // up to ~4.6° lean at max wind
      const sprW = dinoSize.w * PIXEL_SCALE
      const sprH = dinoSize.h * PIXEL_SCALE
      const offscreen = document.createElement('canvas')
      offscreen.width = sprW
      offscreen.height = sprH
      const offCtx = offscreen.getContext('2d')!
      drawSprite(offCtx, dinoSprite, 0, 0, PIXEL_SCALE, framePalette)
      // Rotate around dino's feet (bottom-center)
      const footX = dinoDrawX + sprW / 2
      const footY = dinoDrawY + sprH
      ctx.save()
      ctx.imageSmoothingEnabled = false
      ctx.translate(footX, footY)
      ctx.rotate(-lean)
      ctx.translate(-footX, -footY)
      ctx.drawImage(offscreen, dinoDrawX, dinoDrawY)
      ctx.restore()
    } else {
      drawSprite(ctx, dinoSprite, dinoDrawX, dinoDrawY, PIXEL_SCALE, framePalette)
    }

    // --- Weather effects ---
    if (weather.type !== 'none' && weather.intensity > 0) {
      // Sandstorm: brownish overlay tint
      if (weather.type === 'sandstorm') {
        ctx.globalAlpha = weather.intensity * 0.15
        ctx.fillStyle = '#8b6914'
        ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        ctx.globalAlpha = 1
      }
      // Thunderstorm: dark overcast tint
      if (weather.type === 'thunderstorm') {
        ctx.globalAlpha = weather.intensity * 0.18
        ctx.fillStyle = '#1a1a2a'
        ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        ctx.globalAlpha = 1
      }
      // Snowstorm: slight white-blue overlay
      if (weather.type === 'snowstorm') {
        ctx.globalAlpha = weather.intensity * 0.1
        ctx.fillStyle = '#c0d0e8'
        ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        ctx.globalAlpha = 1
      }

      // Draw particles (depth affects opacity and line width for rain/snow)
      for (const p of weather.particles) {
        const d = p.depth
        if (weather.type === 'rain' || weather.type === 'thunderstorm') {
          ctx.globalAlpha = weather.intensity * (0.3 + d * 0.5)
          ctx.strokeStyle = nt > 0.5 ? '#6688bb' : '#4477aa'
          ctx.lineWidth = (weather.type === 'thunderstorm' ? 1.5 : 1) * d
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(p.x + p.vx * 2, p.y + p.vy * 2)
          ctx.stroke()
        } else if (weather.type === 'sandstorm') {
          ctx.globalAlpha = weather.intensity * 0.8
          ctx.fillStyle = `rgba(180, 140, 60, ${0.3 + p.size * 0.15})`
          ctx.fillRect(p.x, p.y, p.size * 2, p.size)
        } else if (weather.type === 'meteor-shower') {
          ctx.globalAlpha = weather.intensity * (0.3 + d * 0.5)
          // Trail length and brightness scale with depth
          const trail = 4 + d * 4
          const gradient = ctx.createLinearGradient(
            p.x, p.y, p.x - p.vx * trail, p.y - p.vy * trail,
          )
          gradient.addColorStop(0, d > 0.7 ? '#ffffff' : '#ffcc66')
          gradient.addColorStop(0.3, d > 0.7 ? '#ffaa33' : '#cc7722')
          gradient.addColorStop(1, 'transparent')
          ctx.strokeStyle = gradient
          ctx.lineWidth = p.size
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(p.x - p.vx * trail, p.y - p.vy * trail)
          ctx.stroke()
          // Bright head only on close/intense meteors
          if (d > 0.6) {
            ctx.fillStyle = '#ffffff'
            const hs = Math.round(1 + d * 2)
            ctx.fillRect(p.x - 1, p.y - 1, hs, hs)
          }
        } else if (weather.type === 'snowstorm') {
          ctx.globalAlpha = weather.intensity * (0.4 + d * 0.4)
          ctx.fillStyle = '#e8eef8'
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      ctx.globalAlpha = 1
    }

    // --- Meteor ground impacts ---
    if (weather.impacts.length > 0) {
      for (const imp of weather.impacts) {
        const t = imp.age / imp.maxAge
        const radius = imp.size * (0.3 + t * 0.7)
        const alpha = (1 - t) * 0.7
        if (alpha <= 0 || radius <= 0) continue
        ctx.globalAlpha = alpha
        const grad = ctx.createRadialGradient(imp.x - camShift, imp.y, 0, imp.x - camShift, imp.y, radius)
        grad.addColorStop(0, '#ffffff')
        grad.addColorStop(0.3, '#ffaa33')
        grad.addColorStop(0.7, '#ff4400')
        grad.addColorStop(1, 'transparent')
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(imp.x - camShift, imp.y, radius, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    // --- Lightning flash ---
    if (weather.lightning > 0) {
      ctx.globalAlpha = (weather.lightning / 18) * 0.35
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
      ctx.globalAlpha = 1
    }

    // --- Score popups (floating +XX) ---
    const camShiftScore = getCameraShift(state.speed)
    for (const pop of state.scorePopups) {
      const t = pop.age / pop.maxAge
      const alpha = Math.min(1, (1 - t) * 1.5)
      const rise = t * 30
      if (alpha <= 0) continue
      ctx.globalAlpha = alpha
      ctx.font = 'bold 15px monospace'
      ctx.textAlign = 'center'
      const px = pop.x - camShiftScore
      const py = pop.y - rise
      // Dark outline for contrast
      ctx.strokeStyle = '#000000'
      ctx.lineWidth = 3
      ctx.strokeText(pop.text, px, py)
      ctx.fillStyle = '#ffee55'
      ctx.fillText(pop.text, px, py)
    }
    ctx.globalAlpha = 1

    // --- Score ---
    const scoreColor = lerpColor('#535353', '#cccccc', nt)
    ctx.fillStyle = scoreColor
    ctx.font = 'bold 14px monospace'
    ctx.textAlign = 'right'
    const scoreText = String(Math.floor(state.score)).padStart(5, '0')
    const hiText = `HI ${String(Math.floor(state.highScore)).padStart(5, '0')}`

    // Milestone flash
    if (state.milestoneFlash > 0 && state.milestoneFlash % 4 < 2) {
      ctx.fillStyle = 'transparent'
    }
    ctx.fillText(scoreText, CANVAS_WIDTH - 10, 24)
    ctx.fillStyle = lerpColor('#757575', '#999999', nt)
    ctx.fillText(hiText, CANVAS_WIDTH - 80, 24)

    // Weather multiplier badge
    const mult = getWeatherMultiplier(state.weather)
    if (mult > 1.01 && state.phase === 'playing') {
      ctx.font = 'bold 11px monospace'
      ctx.fillStyle = '#ffdd44'
      ctx.globalAlpha = Math.min(1, state.weather.intensity * 1.5)
      ctx.fillText(`×${mult.toFixed(1)}`, CANVAS_WIDTH - 10, 38)
      ctx.globalAlpha = 1
    }

    // --- Waiting overlay ---
    if (state.phase === 'waiting') {
      ctx.fillStyle = lerpColor('#535353', '#cccccc', nt)
      ctx.font = 'bold 16px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('Press SPACE to Start', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10)
      ctx.font = '12px monospace'
      ctx.fillText('SPACE / Tap = Jump  |  DOWN = Duck', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 15)
    }

    // --- Game over overlay ---
    if (state.phase === 'dead') {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)'
      ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 20px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('GAME OVER', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10)
      ctx.font = '13px monospace'
      ctx.fillText('Press SPACE to restart', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 15)
    }
  }, [])

  // -----------------------------------------------------------------------
  // Game loop
  // -----------------------------------------------------------------------

  const gameLoop = useCallback(() => {
    const state = stateRef.current
    const input = autoPlayRef.current ? computeAutoInput(state) : inputRef.current
    const next = update(state, input)
    stateRef.current = next

    // Auto-play: auto-restart on death
    if (autoPlayRef.current && next.phase === 'dead') {
      const hi = Math.max(bestScore, Math.floor(next.highScore))
      stateRef.current = createGame(hi, next.rhythmMode)
      stateRef.current = { ...stateRef.current, phase: 'waiting' }
      render(stateRef.current)
      rafRef.current = requestAnimationFrame(gameLoop)
      return
    }

    // Sync React state only when needed
    if (next.phase !== state.phase) {
      if (next.phase === 'dead') {
        gameStatusRef.current = 'lost'
        setGameStatus('lost')
        saveScore('dino-runner', Math.floor(next.score))
        sfx.play('die')
      } else if (next.phase === 'playing' && state.phase === 'waiting') {
        gameStatusRef.current = 'playing'
        setGameStatus('playing')
        music.start()
      }
    }
    // Detect score milestones (every 100 points)
    if (next.milestoneFlash > 0 && state.milestoneFlash === 0) {
      sfx.play('score')
    }
    // Update music parameters (every 10 frames to avoid thrashing)
    if (next.phase === 'playing' && next.frameCount % 10 === 0) {
      music.updateParams({
        speed: next.speed,
        score: next.score,
        isNight: next.nightTransition,
        weather: next.weather.type,
      })
    }
    // Update score display periodically (every 5 frames to reduce renders)
    if (next.frameCount % 5 === 0 || next.phase === 'dead') {
      setDisplayScore(Math.floor(next.score))
      setDisplayHigh(Math.floor(next.highScore))
    }

    render(next)
    rafRef.current = requestAnimationFrame(gameLoop)
  }, [render, saveScore])

  const restartGame = useCallback(() => {
    const hi = Math.max(bestScore, Math.floor(stateRef.current.highScore))
    stateRef.current = createGame(hi, rhythmMode)
    inputRef.current = { jump: false, duck: false }
    gameStatusRef.current = 'idle'
    setGameStatus('idle')
    setDisplayScore(0)
  }, [bestScore, rhythmMode])

  // -----------------------------------------------------------------------
  // Keyboard controls
  // -----------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'ArrowUp') {
        e.preventDefault()
        music.init() // safe to call repeatedly; only inits once
        sfx.init()
        if (gameStatusRef.current === 'lost') {
          restartGame()
          return
        }
        inputRef.current.jump = true
        sfx.play('jump')
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        inputRef.current.duck = true
      }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'ArrowUp') {
        inputRef.current.jump = false
      }
      if (e.key === 'ArrowDown') {
        inputRef.current.duck = false
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [restartGame])

  // -----------------------------------------------------------------------
  // Touch controls
  // -----------------------------------------------------------------------

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let jumpTimer: ReturnType<typeof setTimeout> | null = null

    const handleTouchStart = (e: TouchEvent) => {
      e.preventDefault()
      music.init() // safe to call repeatedly; only inits once
      sfx.init()
      const t = e.touches[0]
      touchStartRef.current = { x: t.clientX, y: t.clientY }

      if (gameStatusRef.current === 'lost') {
        restartGame()
        return
      }
      // Delay jump to give touchmove a chance to detect swipe-down (duck)
      if (jumpTimer) clearTimeout(jumpTimer)
      jumpTimer = setTimeout(() => {
        if (!inputRef.current.duck) {
          inputRef.current.jump = true
          sfx.play('jump')
        }
        jumpTimer = null
      }, 80)
    }
    const handleTouchMove = (e: TouchEvent) => {
      if (!touchStartRef.current || e.touches.length === 0) return
      const t = e.touches[0]
      const dy = t.clientY - touchStartRef.current.y
      if (dy > 20) {
        // Swiping down — duck, cancel pending jump
        if (jumpTimer) { clearTimeout(jumpTimer); jumpTimer = null }
        inputRef.current.jump = false
        inputRef.current.duck = true
      } else if (dy < -10) {
        // Swiping up — ensure jump
        inputRef.current.duck = false
        if (!inputRef.current.jump) {
          inputRef.current.jump = true
          sfx.play('jump')
        }
      }
    }
    const handleTouchEnd = () => {
      // If jump timer is still pending, it was a quick tap — fire a short jump
      if (jumpTimer) {
        clearTimeout(jumpTimer)
        jumpTimer = null
        if (!inputRef.current.duck) {
          inputRef.current.jump = true
          sfx.play('jump')
          // Release after one frame so the dino gets minimum jump height
          requestAnimationFrame(() => { inputRef.current.jump = false })
        }
      } else {
        // Finger lifted — release jump (ends variable-height hold)
        inputRef.current.jump = false
      }
      inputRef.current.duck = false
      touchStartRef.current = null
    }

    canvas.addEventListener('touchstart', handleTouchStart, { passive: false })
    canvas.addEventListener('touchmove', handleTouchMove, { passive: true })
    canvas.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart)
      canvas.removeEventListener('touchmove', handleTouchMove)
      canvas.removeEventListener('touchend', handleTouchEnd)
    }
  }, [restartGame, isLandscape])

  // -----------------------------------------------------------------------
  // Animation frame loop
  // -----------------------------------------------------------------------

  useEffect(() => {
    render(stateRef.current)
    rafRef.current = requestAnimationFrame(gameLoop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [gameLoop, render])

  // -----------------------------------------------------------------------
  // Responsive canvas scaling
  // -----------------------------------------------------------------------

  const toggleAutoPlay = useCallback(() => {
    const next = !autoPlayRef.current
    autoPlayRef.current = next
    setAutoPlay(next)
    if (next) {
      // Auto-start if idle or dead
      const phase = stateRef.current.phase
      if (phase === 'waiting' || phase === 'dead') {
        const hi = Math.max(bestScore, Math.floor(stateRef.current.highScore))
        stateRef.current = createGame(hi, stateRef.current.rhythmMode)
        inputRef.current = { jump: false, duck: false }
        gameStatusRef.current = 'idle'
        setGameStatus('idle')
      }
    }
  }, [bestScore])

  const toggleRhythmMode = useCallback(() => {
    setRhythmMode(prev => {
      const next = !prev
      // Restart game with new mode
      const hi = Math.max(bestScore, Math.floor(stateRef.current.highScore))
      stateRef.current = createGame(hi, next)
      inputRef.current = { jump: false, duck: false }
      gameStatusRef.current = 'idle'
      setGameStatus('idle')
      setDisplayScore(0)
      return next
    })
  }, [bestScore])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={toggleAutoPlay}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            autoPlay
              ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
              : 'bg-slate-700/50 text-slate-400 border border-slate-600/30 hover:bg-slate-700'
          }`}
        >
          {autoPlay ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
          View Mode
        </button>
        <button
          onClick={toggleRhythmMode}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            rhythmMode
              ? 'bg-purple-600/20 text-purple-400 border border-purple-500/30'
              : 'bg-slate-700/50 text-slate-400 border border-slate-600/30 hover:bg-slate-700'
          }`}
        >
          <Music className="w-3 h-3" />
          Rhythm
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
      <span className="text-xs text-slate-500">
        {autoPlay ? 'AI is playing — sit back and watch'
          : rhythmMode ? 'Rhythm Mode — obstacles sync to the beat'
          : 'Space / Tap = Jump  |  Down = Duck'}
      </span>
    </div>
  )

  return (
    <GameLayout title="Dino Runner" score={displayScore} bestScore={displayHigh} controls={controls}>
      {/*
        Canvas wrapper: in landscape, goes fullscreen via fixed positioning.
        Canvas stays in the same React tree position — no unmount/remount,
        so refs and event listeners survive orientation changes.
      */}
      <div
        className={isLandscape
          ? 'fixed inset-0 z-50 bg-black flex items-center justify-center'
          : 'relative flex flex-col items-center space-y-4'
        }
        style={isLandscape ? { touchAction: 'none' } : undefined}
      >
        <canvas
          ref={canvasRef}
          width={CANVAS_WIDTH}
          height={CANVAS_HEIGHT}
          className={isLandscape ? '' : 'rounded-lg border border-slate-700 w-full'}
          style={{
            maxWidth: isLandscape ? undefined : CANVAS_WIDTH,
            touchAction: 'none',
            imageRendering: 'pixelated',
            ...(isLandscape ? { width: '100vw', height: '100vh', objectFit: 'contain' } : {}),
          }}
        />
        {!isLandscape && (
          <p className="text-xs text-slate-500 sm:hidden">
            Tap to jump. Swipe down to duck.
          </p>
        )}
        {gameStatus === 'lost' && !autoPlay && (
          <GameOverModal
            status="lost"
            score={displayScore}
            bestScore={displayHigh}
            onPlayAgain={restartGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
