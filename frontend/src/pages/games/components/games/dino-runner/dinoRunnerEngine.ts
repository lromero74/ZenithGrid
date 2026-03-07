/**
 * Dino Runner game engine — pure functions, no React dependencies.
 *
 * Pixel-art endless runner inspired by Chrome's T-Rex game.
 * All game logic is pure: no side effects, no canvas references, fully testable.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DinoState {
  x: number
  y: number
  vy: number
  ducking: boolean
  dead: boolean
  frame: number
}

export type ObstacleType = 'cactus-small' | 'cactus-tall' | 'cactus-group' | 'pterodactyl'

export interface Obstacle {
  type: ObstacleType
  x: number
  y: number
  frame: number
  scored?: boolean
}

export interface Cloud {
  x: number
  y: number
  speed: number
  spriteIndex: number
  scale: number
}

export interface Star {
  x: number
  y: number
  speed: number // drift speed multiplier
  size: number  // 1–2 pixel size
}

export interface GroundParticle {
  x: number
  y: number      // offset below GROUND_Y (0 = surface, ~35 = bottom)
  size: number    // 1–3 px
  layer: number   // 0 = surface (1× speed), 1 = mid (1.3×), 2 = deep (1.6×)
  bright: boolean // true = highlight/white speck, false = dirt-colored
}

export interface InputState {
  jump: boolean
  duck: boolean
}

export interface Hitbox {
  x: number
  y: number
  w: number
  h: number
}

export type WeatherType = 'none' | 'rain' | 'thunderstorm' | 'sandstorm' | 'meteor-shower' | 'snowstorm'

export interface WeatherParticle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  depth: number // 0 = far/distant, 1 = close/foreground
}

export interface MeteorImpact {
  x: number
  y: number
  age: number
  maxAge: number
  size: number
}

export interface StormCloud {
  x: number
  y: number
  w: number
  h: number
  speed: number
  spriteIndex: number
}

export interface WeatherState {
  type: WeatherType
  timer: number
  intensity: number
  particles: WeatherParticle[]
  lightning: number
  stormClouds: StormCloud[]
  impacts: MeteorImpact[]
  windStrength: number // 0–1, rolled per event — scales drag and visual push
}

export interface BiomeLayer {
  heights: number[]
  dayColor: string
  nightColor: string
  step: number
}

export interface Biome {
  name: string
  far: BiomeLayer
  mid: BiomeLayer
  near: BiomeLayer
  groundDay: string
  groundNight: string
  accentDay: string
  accentNight: string
  lineDay: string
  lineNight: string
  obsOutlineDay: string
  obsOutlineNight: string
  obsFillDay: string
  obsFillNight: string
}

export interface ScorePopup {
  x: number
  y: number
  text: string
  age: number
  maxAge: number
}

export interface ParallaxState {
  biomeIndex: number
  prevBiomeIndex: number
  transitionProgress: number
  farOffset: number
  midOffset: number
  nearOffset: number
  nextBiomeScore: number
}

export interface GameState {
  dino: DinoState
  obstacles: Obstacle[]
  clouds: Cloud[]
  stars: Star[]
  ground: { offset: number; particles: GroundParticle[] }
  score: number
  highScore: number
  speed: number
  phase: 'waiting' | 'playing' | 'dead'
  nightMode: boolean
  nightTransition: number
  frameCount: number
  nextObstacleDistance: number
  milestoneFlash: number
  weather: WeatherState
  nextWeatherCheck: number
  parallax: ParallaxState
  scorePopups: ScorePopup[]
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const CANVAS_WIDTH = 600
export const CANVAS_HEIGHT = 200
export const PIXEL_SCALE = 3
export const GROUND_Y = CANVAS_HEIGHT - 40
export const GRAVITY = 0.6
export const JUMP_VELOCITY = -11
export const HOLD_GRAVITY_FACTOR = 0.6
export const INITIAL_SPEED = 2.5
export const SPEED_INCREMENT = 0.001125
export const MAX_SPEED = 6
export const MIN_OBSTACLE_GAP = 300
export const NIGHT_TOGGLE_INTERVAL = 4500
export const NIGHT_TRANSITION_FRAMES = 3600
export const PTERO_MIN_SCORE = 300
export const MILESTONE_INTERVAL = 100
export const HITBOX_INSET = 0.8
export const DINO_X = 50

// Weather events
export const WEATHER_MIN_SCORE = 600
export const WEATHER_CHECK_INTERVAL = 1200
export const WEATHER_DURATION_MIN = 1200
export const WEATHER_DURATION_MAX = 3600
export const WEATHER_RAMP_FRAMES = 300
export const WEATHER_CHANCE = 0.2

// Parallax biomes
export const BIOME_CHANGE_MIN = 300
export const BIOME_CHANGE_MAX = 900
export const BIOME_TRANSITION_FRAMES = 180
// Scoring
export const OBSTACLE_BONUS: Record<ObstacleType, number> = {
  'cactus-small': 10,
  'cactus-tall': 15,
  'cactus-group': 20,
  'pterodactyl': 25,
}

export const WEATHER_SCORE_MULT: Record<WeatherType, number> = {
  'none': 1, 'rain': 1.2, 'thunderstorm': 1.5,
  'sandstorm': 1.5, 'meteor-shower': 1.3, 'snowstorm': 1.3,
}

/** Get current score multiplier (scales with weather intensity). */
export function getWeatherMultiplier(weather: WeatherState): number {
  const base = WEATHER_SCORE_MULT[weather.type] ?? 1
  return 1 + (base - 1) * weather.intensity
}

export const FAR_SPEED = 0.12
export const MID_SPEED = 0.3
export const NEAR_SPEED = 0.55

// Ground dirt particle layer speeds (multipliers of base ground speed)
export const GROUND_LAYER_SPEEDS = [1.0, 1.3, 1.6]
const GROUND_PARTICLE_COUNT = 80

function generateTerrain(
  length: number, base: number,
  waves: [number, number, number][],
): number[] {
  // Snap each wave frequency to the nearest whole-cycle multiple of 2π/length.
  // This makes sin(0) == sin(length) so the terrain tiles seamlessly.
  const snapped = waves.map(([amp, freq, phase]) => {
    const cycles = Math.max(1, Math.round(freq * length / (2 * Math.PI)))
    return [amp, (2 * Math.PI * cycles) / length, phase] as [number, number, number]
  })
  const h: number[] = []
  for (let i = 0; i < length; i++) {
    let v = base
    for (const [amp, freq, phase] of snapped) v += Math.sin(i * freq + phase) * amp
    h.push(Math.max(0, Math.round(v)))
  }
  return h
}

export const BIOMES: Biome[] = [
  { // Mountains — gray-blue rocky terrain
    name: 'mountains',
    far:  { heights: generateTerrain(200, 28, [[18, 0.02, 0], [12, 0.05, 1.5], [4, 0.11, 3]]), dayColor: '#7888a0', nightColor: '#252538', step: 5 },
    mid:  { heights: generateTerrain(250, 16, [[10, 0.04, 0.5], [7, 0.09, 2], [3, 0.18, 4]]), dayColor: '#5a7a5a', nightColor: '#1a2828', step: 4 },
    near: { heights: generateTerrain(200, 9, [[5, 0.08, 0], [3, 0.22, 1], [6, 0.45, 2]]), dayColor: '#3a5a3a', nightColor: '#101a18', step: 3 },
    groundDay: '#7a7068', groundNight: '#2a2830',
    accentDay: '#9a9088', accentNight: '#4a4858',
    lineDay: '#5a5048', lineNight: '#2a2838',
    obsOutlineDay: '#4a4a52', obsOutlineNight: '#2a2a32',
    obsFillDay: '#6a6a72', obsFillNight: '#3a3a42',
  },
  { // Forest — earthy brown-green
    name: 'forest',
    far:  { heights: generateTerrain(200, 20, [[8, 0.03, 0], [5, 0.07, 1.2]]), dayColor: '#6a9a6a', nightColor: '#1a2a28', step: 5 },
    mid:  { heights: generateTerrain(250, 24, [[6, 0.05, 0.8], [4, 0.13, 2.5], [5, 0.28, 4]]), dayColor: '#3a7a3a', nightColor: '#0a2018', step: 4 },
    near: { heights: generateTerrain(200, 13, [[4, 0.08, 0], [3, 0.22, 1.5], [5, 0.4, 3]]), dayColor: '#2a5a2a', nightColor: '#081a10', step: 3 },
    groundDay: '#5a4a30', groundNight: '#1a1818',
    accentDay: '#7a6a48', accentNight: '#3a3028',
    lineDay: '#3a2a18', lineNight: '#1a1010',
    obsOutlineDay: '#3a4a2a', obsOutlineNight: '#1a2818',
    obsFillDay: '#5a6a3a', obsFillNight: '#2a3820',
  },
  { // Plains — golden wheat
    name: 'plains',
    far:  { heights: generateTerrain(200, 7, [[4, 0.02, 0], [2, 0.06, 1]]), dayColor: '#a09870', nightColor: '#2a2828', step: 5 },
    mid:  { heights: generateTerrain(250, 9, [[5, 0.04, 0.5], [3, 0.1, 2]]), dayColor: '#808a58', nightColor: '#1a2018', step: 4 },
    near: { heights: generateTerrain(200, 5, [[3, 0.07, 0], [2, 0.18, 1.5], [1, 0.45, 3]]), dayColor: '#607040', nightColor: '#101810', step: 3 },
    groundDay: '#a89060', groundNight: '#3a3828',
    accentDay: '#c8b078', accentNight: '#5a4838',
    lineDay: '#887040', lineNight: '#2a2818',
    obsOutlineDay: '#5a6030', obsOutlineNight: '#2a2818',
    obsFillDay: '#7a8848', obsFillNight: '#3a4028',
  },
  { // Desert — sandy, classic cactus territory
    name: 'desert',
    far:  { heights: generateTerrain(200, 20, [[14, 0.015, 0], [6, 0.04, 1.8]]), dayColor: '#c0a070', nightColor: '#302820', step: 5 },
    mid:  { heights: generateTerrain(250, 12, [[8, 0.025, 0.5], [4, 0.07, 2.2]]), dayColor: '#a08858', nightColor: '#282018', step: 4 },
    near: { heights: generateTerrain(200, 6, [[4, 0.04, 0], [2, 0.14, 1.5]]), dayColor: '#887048', nightColor: '#201810', step: 3 },
    groundDay: '#c0a060', groundNight: '#4a3828',
    accentDay: '#d8b870', accentNight: '#5a4838',
    lineDay: '#8a7040', lineNight: '#3a2818',
    obsOutlineDay: '#5c3d1a', obsOutlineNight: '#3a2a18',
    obsFillDay: '#8c6b3a', obsFillNight: '#4a3a28',
  },
  { // Jungle — dark tropical
    name: 'jungle',
    far:  { heights: generateTerrain(200, 30, [[10, 0.03, 0], [5, 0.07, 1.3]]), dayColor: '#508878', nightColor: '#1a2828', step: 5 },
    mid:  { heights: generateTerrain(250, 32, [[6, 0.04, 0.7], [4, 0.12, 2], [5, 0.24, 3.5]]), dayColor: '#286828', nightColor: '#082018', step: 4 },
    near: { heights: generateTerrain(200, 16, [[5, 0.06, 0], [4, 0.17, 1.2], [5, 0.35, 2.8]]), dayColor: '#1a4a1a', nightColor: '#061408', step: 3 },
    groundDay: '#4a3a20', groundNight: '#1a1410',
    accentDay: '#6a5a38', accentNight: '#3a2a18',
    lineDay: '#3a2a10', lineNight: '#100a08',
    obsOutlineDay: '#1a5a3a', obsOutlineNight: '#0a2818',
    obsFillDay: '#2a7a5a', obsFillNight: '#1a3828',
  },
  { // Snow/Glacier — icy whites and blues
    name: 'snow',
    far:  { heights: generateTerrain(200, 22, [[15, 0.02, 0.3], [8, 0.05, 2]]), dayColor: '#b0c0d8', nightColor: '#2a2a3a', step: 5 },
    mid:  { heights: generateTerrain(250, 14, [[8, 0.035, 0.6], [5, 0.09, 1.8]]), dayColor: '#90a8c0', nightColor: '#1a2030', step: 4 },
    near: { heights: generateTerrain(200, 8, [[4, 0.06, 0], [3, 0.16, 1.2]]), dayColor: '#7090a8', nightColor: '#102028', step: 3 },
    groundDay: '#d0d8e8', groundNight: '#4a4a5a',
    accentDay: '#e8f0f8', accentNight: '#6a6a7a',
    lineDay: '#a0a8b8', lineNight: '#3a3a4a',
    obsOutlineDay: '#4060a0', obsOutlineNight: '#2a3858',
    obsFillDay: '#6888c0', obsFillNight: '#3a4868',
  },
]

// ---------------------------------------------------------------------------
// Color Palette
// ---------------------------------------------------------------------------

export const PALETTE: Record<number, string> = {
  0: 'transparent',
  1: '#2d5a1e',  // dark green — outline
  2: '#4a8c2a',  // medium green — body fill
  3: '#7ec850',  // light green — belly/highlights
  4: '#ffffff',  // white — eye
  5: '#1a1a1a',  // black — pupil, mouth
  6: '#5c3d1a',  // dark brown — cactus outline
  7: '#8c6b3a',  // medium brown — cactus fill
  8: '#c4a055',  // light brown — ground highlights
  9: '#cc3333',  // red — pterodactyl accents
  10: '#555555', // dark gray — pterodactyl body
  11: '#e67300', // orange — eye detail
}

// ---------------------------------------------------------------------------
// Sprite Data — 2D number arrays (0 = transparent, 1+ = palette index)
// ---------------------------------------------------------------------------

/** Dino run frame 1 — right leg forward (10w x 12h) */
export const DINO_RUN1: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
  [0, 0, 1, 0, 0, 0, 1, 1, 0, 0],
]

/** Dino run frame 2 — left leg forward (10w x 12h) */
export const DINO_RUN2: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 1, 0, 0, 0],
  [0, 0, 0, 1, 1, 0, 1, 0, 0, 0],
]

/** Dino jump — legs tucked (10w x 12h) */
export const DINO_JUMP: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 1, 1, 0, 0, 0],
  [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]

/** Dino duck frame 1 (14w x 7h) */
export const DINO_DUCK1: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 2, 5, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 0, 0],
  [0, 0, 1, 2, 3, 3, 2, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0],
]

/** Dino duck frame 2 (14w x 7h) */
export const DINO_DUCK2: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 2, 5, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 0, 0],
  [0, 0, 1, 2, 3, 3, 2, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0],
]

/** Dino dead — X-eyes (10w x 12h) */
export const DINO_DEAD: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 5, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 4, 5, 4, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 5, 1, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
  [0, 0, 1, 0, 0, 0, 1, 1, 0, 0],
]

/** Cactus small (5w x 10h) */
export const CACTUS_SMALL: number[][] = [
  [0, 0, 6, 0, 0],
  [0, 0, 7, 0, 0],
  [6, 0, 7, 0, 0],
  [7, 6, 7, 0, 0],
  [7, 0, 7, 0, 6],
  [6, 0, 7, 6, 7],
  [0, 0, 7, 0, 6],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 6, 7, 6, 0],
]

/** Cactus tall (5w x 14h) */
export const CACTUS_TALL: number[][] = [
  [0, 0, 6, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [6, 0, 7, 0, 0],
  [7, 6, 7, 0, 0],
  [7, 0, 7, 0, 6],
  [6, 0, 7, 6, 7],
  [0, 0, 7, 0, 6],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 6, 7, 6, 0],
]

/** Cactus group — cluster of 3 (11w x 10h) */
export const CACTUS_GROUP: number[][] = [
  [0, 0, 6, 0, 0, 0, 6, 0, 0, 0, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 6, 0],
  [6, 0, 7, 0, 6, 0, 7, 0, 0, 7, 0],
  [7, 6, 7, 0, 7, 6, 7, 0, 6, 7, 0],
  [6, 0, 7, 0, 6, 0, 7, 0, 7, 7, 6],
  [0, 0, 7, 0, 0, 0, 7, 0, 6, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 6, 7, 6, 0, 6, 7, 6, 6, 7, 6],
]

/** Pterodactyl wing up (12w x 8h) */
export const PTERO_UP: number[][] = [
  [0, 0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 10, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 10, 10, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 10, 10, 10, 10, 10, 10, 10, 10,  9, 10, 10],
  [10, 0, 0, 0, 10, 10, 10, 10, 11,  9, 10, 10],
  [0, 0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 0],
  [0, 0, 0, 0, 0, 0, 10, 10, 0, 0, 0, 0],
]

/** Pterodactyl wing down (12w x 8h) */
export const PTERO_DOWN: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 10, 10, 10, 10, 10, 10, 10, 10,  9, 10, 10],
  [10, 0, 0, 10, 10, 10, 10, 10, 11,  9, 10, 10],
  [0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 0, 0, 0, 10, 10, 0, 0, 0, 0, 0, 0],
]

/**
 * Cloud sprites — all pixel art. Regular clouds use palette color 4 (white).
 * Weather clouds use indexed tones: rain 2-tone (1=body, 2=shadow),
 * storm 3-tone (1=highlight, 2=body, 3=dark underside).
 */
export const WEATHER_CLOUD_SCALE = 4

/** Regular cloud A — classic two-bump (16w × 5h) */
const CLOUD_A: number[][] = [
  [0,0,0,4,4,0,0,0,0,4,4,0,0,0,0,0],
  [0,0,4,4,4,4,0,0,4,4,4,4,4,0,0,0],
  [0,4,4,4,4,4,4,4,4,4,4,4,4,4,0,0],
  [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,0],
  [0,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
]
/** Regular cloud B — wide flat (20w × 4h) */
const CLOUD_B: number[][] = [
  [0,0,0,0,0,4,4,0,0,0,0,0,4,4,4,0,0,0,0,0],
  [0,0,4,4,4,4,4,4,0,0,4,4,4,4,4,4,4,0,0,0],
  [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,0],
  [0,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
]
/** Regular cloud C — small puff (10w × 4h) */
const CLOUD_C: number[][] = [
  [0,0,0,4,4,4,0,0,0,0],
  [0,0,4,4,4,4,4,4,0,0],
  [4,4,4,4,4,4,4,4,4,0],
  [0,4,4,4,4,4,4,4,4,4],
]
/** Regular cloud D — tall single bump (12w × 5h) */
const CLOUD_D: number[][] = [
  [0,0,0,0,4,4,4,0,0,0,0,0],
  [0,0,4,4,4,4,4,4,4,0,0,0],
  [0,4,4,4,4,4,4,4,4,0,0,0],
  [4,4,4,4,4,4,4,4,4,4,4,0],
  [0,4,4,4,4,4,4,4,4,4,4,4],
]
/** Regular cloud E — long wisp (18w × 3h) */
const CLOUD_E: number[][] = [
  [0,0,0,4,4,0,0,0,0,0,0,4,4,0,0,0,0,0],
  [0,4,4,4,4,4,4,0,4,4,4,4,4,4,4,0,0,0],
  [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
]
export const CLOUD_SPRITES: number[][][] = [CLOUD_A, CLOUD_B, CLOUD_C, CLOUD_D, CLOUD_E]

/** Rain cloud A — large (22w × 8h) */
const RAIN_CLOUD_A: number[][] = [
  [0,0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0],
  [0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0,1,1,0,0,0,0],
  [0,0,0,1,1,1,1,1,1,1,1,1,1,1,0,1,1,1,1,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
  [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,2,2,1,1,2,2,1,1,1,2,2,1,1,1,1,2,1,1,1,1,1],
  [0,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,0],
]
/** Rain cloud B — medium (16w × 7h) */
const RAIN_CLOUD_B: number[][] = [
  [0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0],
  [0,0,0,1,1,1,1,1,1,1,0,0,1,1,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
  [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,2,2,1,1,2,1,1,1,2,2,1,1,1,1,1],
  [0,2,2,2,2,2,2,2,2,2,2,2,2,2,2,0],
]
/** Rain cloud C — small (12w × 6h) */
const RAIN_CLOUD_C: number[][] = [
  [0,0,0,1,1,1,1,0,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,0,0,0],
  [0,1,1,1,1,1,1,1,1,1,1,0],
  [1,1,1,1,1,1,1,1,1,1,1,1],
  [1,2,2,1,1,2,1,1,1,1,1,1],
  [0,2,2,2,2,2,2,2,2,2,2,0],
]
/** Rain cloud D — wide shelf (24w × 7h) */
const RAIN_CLOUD_D: number[][] = [
  [0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,1,1,0,0,0,0,0,0],
  [0,0,0,0,0,1,1,1,1,1,1,1,1,0,1,1,1,1,1,0,0,0,0,0],
  [0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
  [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
  [1,1,2,2,1,1,2,2,1,1,1,2,2,1,1,2,2,1,1,1,1,1,1,1],
  [0,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,0],
]
/** Rain cloud E — small round (10w × 6h) */
const RAIN_CLOUD_E: number[][] = [
  [0,0,0,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,0,0,0],
  [0,1,1,1,1,1,1,1,0,0],
  [1,1,1,1,1,1,1,1,1,0],
  [1,2,2,1,1,2,1,1,1,1],
  [0,2,2,2,2,2,2,2,2,0],
]
export const RAIN_CLOUD_SPRITES: number[][][] = [
  RAIN_CLOUD_A, RAIN_CLOUD_B, RAIN_CLOUD_C, RAIN_CLOUD_D, RAIN_CLOUD_E,
]

/** Storm cloud A — large (28w × 11h) */
const STORM_CLOUD_A: number[][] = [
  [0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  [0,0,0,0,0,0,1,1,1,1,2,1,1,1,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
  [0,0,0,0,1,1,1,2,1,1,2,2,1,1,1,0,0,1,1,1,1,1,0,0,0,0,0,0],
  [0,0,0,1,1,2,2,2,2,2,2,2,2,1,1,1,1,1,2,2,1,1,1,1,0,0,0,0],
  [0,0,1,2,2,2,2,2,2,2,2,2,2,2,2,1,1,2,2,2,2,2,1,1,1,0,0,0],
  [0,1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,1,0,0],
  [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,0],
  [2,3,3,3,2,2,3,3,3,2,2,2,3,3,2,2,2,3,3,3,2,2,2,2,2,2,2,2],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0],
  [0,0,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0,0],
]
/** Storm cloud B — medium (22w × 9h) */
const STORM_CLOUD_B: number[][] = [
  [0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0],
  [0,0,0,0,1,1,1,2,1,1,1,1,0,0,0,1,1,0,0,0,0,0],
  [0,0,1,1,1,2,2,2,2,2,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,1,2,2,2,2,2,2,2,2,2,2,1,1,2,2,1,1,1,0,0,0],
  [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,0,0],
  [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,0],
  [2,3,3,3,2,2,3,3,2,2,2,3,3,2,2,2,2,2,2,2,2,2],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  [0,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0],
]
/** Storm cloud C — compact (16w × 8h) */
const STORM_CLOUD_C: number[][] = [
  [0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0],
  [0,0,0,1,1,1,2,1,1,1,0,1,1,0,0,0],
  [0,0,1,1,2,2,2,2,2,1,1,1,1,1,0,0],
  [0,1,2,2,2,2,2,2,2,2,2,2,2,1,1,0],
  [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
  [2,3,3,2,2,3,3,2,2,2,2,2,2,2,2,2],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  [0,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0],
]
/** Storm cloud D — massive (32w × 12h) */
const STORM_CLOUD_D: number[][] = [
  [0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  [0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0],
  [0,0,0,0,1,1,1,1,2,1,1,2,2,1,1,1,1,0,0,1,1,1,1,1,1,1,0,0,0,0,0,0],
  [0,0,0,1,1,2,2,2,2,2,2,2,2,2,1,1,1,1,1,1,2,2,2,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,2,2,2,2,2,2,2,2,2,2,2,2,1,1,2,2,2,2,2,2,2,1,1,1,1,0,0,0],
  [0,1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,1,1,0,0],
  [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,0],
  [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
  [2,3,3,3,3,2,2,3,3,3,2,2,3,3,3,2,2,2,3,3,2,2,3,3,3,2,2,2,2,2,2,2],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0],
  [0,0,0,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0,0],
]
/** Storm cloud E — small dense (14w × 7h) */
const STORM_CLOUD_E: number[][] = [
  [0,0,0,0,1,1,1,1,0,0,0,0,0,0],
  [0,0,1,1,1,2,2,1,1,1,1,0,0,0],
  [0,1,2,2,2,2,2,2,2,2,1,1,0,0],
  [1,2,2,2,2,2,2,2,2,2,2,2,1,0],
  [2,2,2,2,2,2,2,2,2,2,2,2,2,2],
  [3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  [0,3,3,3,3,3,3,3,3,3,3,3,3,0],
]
export const STORM_CLOUD_SPRITES: number[][][] = [
  STORM_CLOUD_A, STORM_CLOUD_B, STORM_CLOUD_C, STORM_CLOUD_D, STORM_CLOUD_E,
]

// ---------------------------------------------------------------------------
// Sprite size helpers
// ---------------------------------------------------------------------------

export function getSpriteSize(sprite: number[][]): { w: number; h: number } {
  return { w: sprite[0].length, h: sprite.length }
}

/** Get the right dino sprite for the current state. */
export function getDinoSprite(dino: DinoState): number[][] {
  if (dino.dead) return DINO_DEAD
  if (dino.ducking) return dino.frame % 10 < 5 ? DINO_DUCK1 : DINO_DUCK2
  if (dino.y < GROUND_Y) return DINO_JUMP
  return dino.frame % 10 < 5 ? DINO_RUN1 : DINO_RUN2
}

/** Get the right pterodactyl sprite for animation frame. */
export function getPteroSprite(frame: number): number[][] {
  return frame % 20 < 10 ? PTERO_UP : PTERO_DOWN
}

/** Get obstacle sprite by type. */
export function getObstacleSprite(obs: Obstacle): number[][] {
  switch (obs.type) {
    case 'cactus-small': return CACTUS_SMALL
    case 'cactus-tall': return CACTUS_TALL
    case 'cactus-group': return CACTUS_GROUP
    case 'pterodactyl': return getPteroSprite(obs.frame)
  }
}

// ---------------------------------------------------------------------------
// Hitbox helpers
// ---------------------------------------------------------------------------

/** Get the inset hitbox for collision detection (80% of visual size). */
export function getHitbox(x: number, y: number, w: number, h: number): Hitbox {
  const insetX = w * (1 - HITBOX_INSET) / 2
  const insetY = h * (1 - HITBOX_INSET) / 2
  return {
    x: x + insetX,
    y: y + insetY,
    w: w * HITBOX_INSET,
    h: h * HITBOX_INSET,
  }
}

/** Get the dino hitbox in canvas pixels. */
export function getDinoHitbox(dino: DinoState): Hitbox {
  const sprite = getDinoSprite(dino)
  const size = getSpriteSize(sprite)
  return getHitbox(
    dino.x,
    dino.y - size.h * PIXEL_SCALE + PIXEL_SCALE,
    size.w * PIXEL_SCALE,
    size.h * PIXEL_SCALE,
  )
}

/** Get an obstacle hitbox in canvas pixels. */
export function getObstacleHitbox(obs: Obstacle): Hitbox {
  const sprite = getObstacleSprite(obs)
  const size = getSpriteSize(sprite)
  const w = size.w * PIXEL_SCALE
  const h = size.h * PIXEL_SCALE
  // Obstacles are anchored at bottom-left at (obs.x, obs.y)
  return getHitbox(obs.x, obs.y - h, w, h)
}

/** Check if two hitboxes overlap. */
export function hitboxesOverlap(a: Hitbox, b: Hitbox): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x &&
         a.y < b.y + b.h && a.y + a.h > b.y
}

/** Check if the dino collides with an obstacle. */
export function checkCollision(dino: DinoState, obstacle: Obstacle): boolean {
  return hitboxesOverlap(getDinoHitbox(dino), getObstacleHitbox(obstacle))
}

// ---------------------------------------------------------------------------
// Random obstacle generation helpers
// ---------------------------------------------------------------------------

function randomObstacleGap(speed: number): number {
  // ~8% chance of a long "breather" gap (4-10 seconds of clear running)
  if (Math.random() < 0.08) {
    const minPx = speed * 240   // ~4 seconds worth at current speed
    const maxPx = speed * 600   // ~10 seconds worth at current speed
    return minPx + Math.random() * (maxPx - minPx)
  }
  const base = Math.max(MIN_OBSTACLE_GAP, 500 - speed * 15)
  return base + Math.random() * 200
}

function randomObstacleType(score: number): ObstacleType {
  const types: ObstacleType[] = ['cactus-small', 'cactus-tall', 'cactus-group']
  if (score >= PTERO_MIN_SCORE) types.push('pterodactyl')
  return types[Math.floor(Math.random() * types.length)]
}

function getObstacleY(type: ObstacleType): number {
  if (type === 'pterodactyl') {
    // Weighted heights: 40% head height (must duck), 30% mid, 30% high (run under)
    const r = Math.random()
    if (r < 0.4) return GROUND_Y - 20       // head height — duck!
    if (r < 0.7) return GROUND_Y - 40       // mid height — jump
    return GROUND_Y - 70                     // high — run under safely
  }
  return GROUND_Y + PIXEL_SCALE
}

// ---------------------------------------------------------------------------
// Weather helpers
// ---------------------------------------------------------------------------

function pickWeatherType(nightMode: boolean, biomeName: string): WeatherType {
  const types: WeatherType[] = ['rain', 'thunderstorm', 'sandstorm']
  if (nightMode) types.push('meteor-shower')
  if (biomeName === 'snow') types.push('snowstorm')
  return types[Math.floor(Math.random() * types.length)]
}

function spawnWeatherParticle(type: WeatherType): WeatherParticle {
  switch (type) {
    case 'rain': {
      // depth: 0.3 (distant, small, slow) → 1.0 (close, big, fast)
      const d = 0.3 + Math.random() * 0.7
      // Spread spawn x wider — distant drops bias further right (ahead of dino)
      const spread = CANVAS_WIDTH + 60 + (1 - d) * CANVAS_WIDTH * 0.6
      return {
        x: Math.random() * spread - 30,
        y: -5,
        vx: (-0.5 - Math.random() * 0.5) * d,
        vy: (3 + Math.random() * 2) * d + 1,
        size: (0.5 + Math.random()) * d + 0.3,
        depth: d,
      }
    }
    case 'thunderstorm': {
      const d = 0.4 + Math.random() * 0.6
      const spread = CANVAS_WIDTH + 100 + (1 - d) * CANVAS_WIDTH * 0.6
      return {
        x: Math.random() * spread - 50,
        y: -5,
        vx: (-3 - Math.random() * 2) * d,
        vy: (6 + Math.random() * 4) * d + 2,
        size: (1 + Math.random()) * d + 0.5,
        depth: d,
      }
    }
    case 'sandstorm':
      return {
        x: CANVAS_WIDTH + 10,
        y: Math.random() * GROUND_Y,
        vx: -4 - Math.random() * 4,
        vy: -1 + Math.random() * 2,
        size: 1 + Math.random() * 2,
        depth: 1,
      }
    case 'meteor-shower': {
      // Varying intensity: dim distant streaks to bright fireballs
      const d = 0.3 + Math.random() * 0.7
      return {
        x: Math.random() * CANVAS_WIDTH * 0.8 + CANVAS_WIDTH * 0.1,
        y: -10,
        vx: (-1.5 - Math.random() * 2) * d,
        vy: (3 + Math.random() * 3) * d + 1,
        size: (1 + Math.random() * 2) * d + 0.5,
        depth: d,
      }
    }
    case 'snowstorm': {
      const d = 0.3 + Math.random() * 0.7
      const spread = CANVAS_WIDTH + 40 + (1 - d) * CANVAS_WIDTH * 0.6
      return {
        x: Math.random() * spread - 20,
        y: -5,
        vx: (-0.5 + Math.random() * 1) * d,
        vy: (1 + Math.random() * 1.5) * d + 0.5,
        size: (1 + Math.random() * 1.5) * d + 0.5,
        depth: d,
      }
    }
    default:
      return { x: 0, y: 0, vx: 0, vy: 0, size: 1, depth: 1 }
  }
}

const WEATHER_MAX_PARTICLES: Record<WeatherType, number> = {
  'none': 0, 'rain': 30, 'thunderstorm': 70, 'sandstorm': 40, 'meteor-shower': 6, 'snowstorm': 50,
}

const WEATHER_SPAWN_RATE: Record<WeatherType, number> = {
  'none': 0, 'rain': 2, 'thunderstorm': 4, 'sandstorm': 2, 'meteor-shower': 1, 'snowstorm': 2,
}

// Target cloud counts per weather type
const WEATHER_TARGET_CLOUDS: Record<WeatherType, number> = {
  'none': 0, 'rain': 4, 'thunderstorm': 14, 'sandstorm': 0, 'meteor-shower': 0, 'snowstorm': 5,
}

/** Spawn a single weather cloud from the right edge for gradual buildup. */
function spawnSingleWeatherCloud(type: WeatherType): StormCloud {
  const isStorm = type === 'thunderstorm' || type === 'snowstorm'
  const sprites = isStorm ? STORM_CLOUD_SPRITES : RAIN_CLOUD_SPRITES
  const spriteIndex = Math.floor(Math.random() * sprites.length)
  const sprite = sprites[spriteIndex]

  if (type === 'thunderstorm') {
    // Pick a random layer: top (large), mid, or low (small, fast)
    const layer = Math.random()
    if (layer < 0.4) {
      // Top layer — large, slow
      const scale = WEATHER_CLOUD_SCALE + 1 + Math.random() * 2
      return {
        x: CANVAS_WIDTH + Math.random() * 100,
        y: Math.random() * 12,
        w: sprite[0].length * scale, h: sprite.length * scale,
        speed: 0.2 + Math.random() * 0.3, spriteIndex,
      }
    } else if (layer < 0.75) {
      // Mid layer — standard
      return {
        x: CANVAS_WIDTH + Math.random() * 80,
        y: 20 + Math.random() * 25,
        w: sprite[0].length * WEATHER_CLOUD_SCALE, h: sprite.length * WEATHER_CLOUD_SCALE,
        speed: 0.4 + Math.random() * 0.4, spriteIndex,
      }
    } else {
      // Low layer — smaller, faster
      const scale = WEATHER_CLOUD_SCALE - 1
      return {
        x: CANVAS_WIDTH + Math.random() * 60,
        y: 45 + Math.random() * 30,
        w: sprite[0].length * scale, h: sprite.length * scale,
        speed: 0.6 + Math.random() * 0.5, spriteIndex,
      }
    }
  }

  // Rain / snowstorm — standard layer
  return {
    x: CANVAS_WIDTH + Math.random() * 80,
    y: 3 + Math.random() * 20,
    w: sprite[0].length * WEATHER_CLOUD_SCALE, h: sprite.length * WEATHER_CLOUD_SCALE,
    speed: 0.3 + Math.random() * 0.4, spriteIndex,
  }
}

function updateWeather(weather: WeatherState, score: number,
                       nightMode: boolean, nextCheck: number,
                       biomeName: string, gameSpeed: number): {
  weather: WeatherState; nextWeatherCheck: number
} {
  let { type, timer, intensity, particles, lightning, stormClouds, impacts, windStrength } = weather
  let nextWeatherCheck = nextCheck

  // Decay lightning flash
  if (lightning > 0) lightning--

  // Age and scroll meteor impacts — they're on the ground, so they scroll with the world
  impacts = impacts.map(i => ({ ...i, x: i.x - gameSpeed, age: i.age + 1 })).filter(i => i.age < i.maxAge && i.x > -50)

  // No weather active — check if we should start one
  if (type === 'none') {
    if (score >= WEATHER_MIN_SCORE) {
      nextWeatherCheck--
      if (nextWeatherCheck <= 0) {
        if (Math.random() < WEATHER_CHANCE) {
          type = pickWeatherType(nightMode, biomeName)
          // Skew toward shorter durations (min of two random rolls)
          const roll = Math.min(Math.random(), Math.random())
          timer = WEATHER_DURATION_MIN +
            Math.floor(roll * (WEATHER_DURATION_MAX - WEATHER_DURATION_MIN))
          intensity = 0
          particles = []
          lightning = 0
          stormClouds = [] // clouds build up gradually during ramp
          // Roll per-event wind strength: base varies by type, then randomized
          const windBase: Record<WeatherType, [number, number]> = {
            'none': [0, 0], 'rain': [0.05, 0.2], 'thunderstorm': [0.4, 1.0],
            'sandstorm': [0.6, 1.0], 'meteor-shower': [0, 0], 'snowstorm': [0.15, 0.5],
          }
          const [wMin, wMax] = windBase[type]
          windStrength = wMin + Math.random() * (wMax - wMin)
        }
        nextWeatherCheck = WEATHER_CHECK_INTERVAL
      }
    }
    return { weather: { type, timer, intensity, particles, lightning, stormClouds, impacts, windStrength }, nextWeatherCheck }
  }

  // Weather active — update
  timer--

  // Ramp intensity: fade out at end takes priority, otherwise ramp up
  if (timer < WEATHER_RAMP_FRAMES) {
    intensity = Math.max(0, timer / WEATHER_RAMP_FRAMES)
  } else if (intensity < 1) {
    intensity = Math.min(1, intensity + 1 / WEATHER_RAMP_FRAMES)
  }

  // Spawn particles based on intensity
  const maxP = WEATHER_MAX_PARTICLES[type]
  const spawnRate = WEATHER_SPAWN_RATE[type]
  if (particles.length < maxP * intensity) {
    for (let i = 0; i < spawnRate; i++) {
      if (particles.length < maxP) {
        particles.push(spawnWeatherParticle(type))
      }
    }
  }

  // Move particles (world scroll shifts everything left, scaled by depth for parallax)
  particles = particles.map(p => ({
    ...p,
    x: p.x + p.vx - gameSpeed * p.depth,
    y: p.y + p.vy,
  }))

  // Meteor-shower: spawn ground impacts when meteors hit the ground
  if (type === 'meteor-shower') {
    const newImpacts: MeteorImpact[] = []
    particles = particles.filter(p => {
      if (p.y >= GROUND_Y - 5) {
        newImpacts.push({
          x: p.x,
          y: GROUND_Y,
          age: 0,
          maxAge: 25 + Math.floor(Math.random() * 35),
          size: p.size * 4 + Math.random() * 8,
        })
        return false
      }
      return true
    })
    impacts = [...impacts, ...newImpacts]
  }

  // Filter off-screen particles (distant rain/snow stops higher — hit ground in the distance)
  particles = particles.filter(p => {
    if (p.x < -30 || p.x > CANVAS_WIDTH + 30 || p.y < -20) return false
    if ((type === 'rain' || type === 'thunderstorm' || type === 'snowstorm') && p.depth < 1) {
      // Distant drops vanish earlier: depth 0.3 → stop at ~100px, depth 1.0 → full ground
      const maxY = GROUND_Y * (0.5 + p.depth * 0.5)
      return p.y < maxY
    }
    return p.y < CANVAS_HEIGHT + 20
  })

  // Lightning during thunderstorms (~0.8% chance per frame when at full intensity)
  if (type === 'thunderstorm' && lightning <= 0 && Math.random() < 0.008 * intensity) {
    lightning = 18
  }

  // Move storm clouds (slow parallax drift)
  stormClouds = stormClouds.map(c => ({ ...c, x: c.x - c.speed }))
    .filter(c => c.x + c.w > -50)

  // Progressive cloud spawning — add clouds proportional to intensity
  const targetClouds = Math.floor(WEATHER_TARGET_CLOUDS[type] * intensity)
  if (stormClouds.length < targetClouds && (type === 'rain' || type === 'thunderstorm' || type === 'snowstorm')) {
    stormClouds.push(spawnSingleWeatherCloud(type))
  }

  // End weather
  if (timer <= 0) {
    return {
      weather: { type: 'none', timer: 0, intensity: 0, particles: [], lightning: 0, stormClouds: [], impacts, windStrength: 0 },
      nextWeatherCheck: WEATHER_CHECK_INTERVAL,
    }
  }

  return { weather: { type, timer, intensity, particles, lightning, stormClouds, impacts, windStrength }, nextWeatherCheck }
}

// ---------------------------------------------------------------------------
// Auto-play AI
// ---------------------------------------------------------------------------

/**
 * Compute AI input for auto-play. Physics-based trajectory prediction.
 *
 * Strategy:
 * 1. Precompute frame-based danger zones for ALL obstacles.
 * 2. Use actual hitbox math to determine: can we stand? duck? or must jump?
 * 3. For jumps: simulate trajectories with varying hold durations, pick minimum.
 * 4. In air: hold jump only if releasing would collide AND holding wouldn't.
 */
export function computeAutoInput(state: GameState): InputState {
  const { dino, obstacles, speed } = state
  const input: InputState = { jump: false, duck: false }

  if (state.phase === 'waiting' || state.phase === 'dead') {
    input.jump = true
    return input
  }

  // Effective speed with weather drag (matches update loop)
  const windDrag = state.weather.windStrength * state.weather.intensity
  const effSpeed = speed * (1 - windDrag * 0.4)
  if (effSpeed <= 0) return input

  // Hitbox constants
  const DW = 10 * PIXEL_SCALE   // 30 — dino width
  const SH = 12 * PIXEL_SCALE   // 36 — standing height
  const DH = 7 * PIXEL_SCALE    // 21 — duck height
  const M = 4                    // safety margin (pixels)
  const LOOK = 120               // look-ahead frames (~2 sec)

  // Precompute danger zones: frame window + vertical hitbox for each obstacle
  type Danger = { fStart: number; fEnd: number; top: number; bot: number }
  const dangers: Danger[] = []
  for (const obs of obstacles) {
    const sp = getObstacleSprite(obs)
    const sz = getSpriteSize(sp)
    const ow = sz.w * PIXEL_SCALE
    const oh = sz.h * PIXEL_SCALE
    if (obs.x + ow <= dino.x) continue  // already passed

    // Frame window when obstacle overlaps dino horizontally
    const fStart = Math.max(0, Math.floor((obs.x - dino.x - DW + M) / effSpeed))
    const fEnd = Math.ceil((obs.x + ow - dino.x - M) / effSpeed)
    if (fEnd < 0) continue

    dangers.push({ fStart, fEnd, top: obs.y - oh + M, bot: obs.y - M })
  }

  if (dangers.length === 0) return input

  // Would dino collide at frame f with bottom at yBot and given height?
  const hits = (f: number, yBot: number, h: number): boolean => {
    const dTop = yBot - h + PIXEL_SCALE + M
    const dBot = yBot + PIXEL_SCALE - M
    for (const d of dangers) {
      if (f >= d.fStart && f <= d.fEnd && dBot > d.top && dTop < d.bot) return true
    }
    return false
  }

  const onGround = dino.y >= GROUND_Y && dino.vy >= 0

  if (onGround) {
    // Find earliest frame where STANDING collides
    let dangerF = -1
    for (let f = 0; f <= LOOK; f++) {
      if (hits(f, GROUND_Y, SH)) { dangerF = f; break }
    }
    if (dangerF < 0) return input  // all clear, do nothing

    // Can we DUCK through the IMMEDIATE danger cluster?
    // Only check the current group — a gap of 10+ frames means a new cluster
    // that the AI will handle on a future frame after this one passes.
    let canDuck = true
    let lastHitF = dangerF
    for (let f = dangerF; f <= LOOK; f++) {
      if (!hits(f, GROUND_Y, SH)) continue
      if (f - lastHitF > 10) break  // new cluster after gap — handle later
      lastHitF = f
      if (hits(f, GROUND_Y, DH)) { canDuck = false; break }
    }
    if (canDuck) {
      // Duck early enough — start ducking when obstacle is within range
      if (dangerF < 30 + effSpeed * 10) input.duck = true
      return input
    }

    // Must JUMP — find minimum hold that clears ALL obstacles
    const reactThresh = 35 + effSpeed * 14
    if (dangerF * effSpeed > reactThresh + 20) return input  // wait, too far

    for (let hold = 0; hold <= 55; hold++) {
      let y = GROUND_Y, vy = JUMP_VELOCITY, safe = true
      for (let f = 1; f <= LOOK; f++) {
        const g = (f <= hold && vy < 0) ? GRAVITY * HOLD_GRAVITY_FACTOR : GRAVITY
        vy += g
        y += vy
        if (y >= GROUND_Y) { y = GROUND_Y; vy = 0 }

        if (y < GROUND_Y) {
          // In air — must clear all obstacles
          if (hits(f, y, SH)) { safe = false; break }
        } else if (f > 5) {
          // Landed — safe if we can stand OR duck through remaining
          for (let ff = f; ff <= Math.min(f + 40, LOOK); ff++) {
            if (hits(ff, GROUND_Y, SH) && hits(ff, GROUND_Y, DH)) {
              safe = false; break
            }
          }
          break
        }
      }
      if (safe) { input.jump = true; return input }
    }

    // No safe hold found — jump max hold as best effort
    input.jump = true
    return input
  }

  // IN AIR — should we hold jump?
  if (dino.vy < 0) {
    // Simulate RELEASING (full gravity) — check trajectory + post-landing ground
    let y = dino.y, vy = dino.vy, releaseHits = false
    for (let f = 1; f <= LOOK; f++) {
      vy += GRAVITY
      y += vy
      if (y >= GROUND_Y) {
        // Landed — check this frame AND next ~40 ground frames for obstacles
        // we can't duck or react to (too close after landing)
        for (let ff = f; ff <= Math.min(f + 40, LOOK); ff++) {
          if (hits(ff, GROUND_Y, SH) && hits(ff, GROUND_Y, DH)) {
            releaseHits = true
            break
          }
        }
        break
      }
      if (hits(f, y, SH)) { releaseHits = true; break }
    }

    if (releaseHits) {
      // Simulate HOLDING — same checks (avoid jumping INTO ptero above)
      let hY = dino.y, hVy = dino.vy, holdHits = false
      for (let f = 1; f <= LOOK; f++) {
        const g = (hVy < 0) ? GRAVITY * HOLD_GRAVITY_FACTOR : GRAVITY
        hVy += g
        hY += hVy
        if (hY >= GROUND_Y) {
          for (let ff = f; ff <= Math.min(f + 40, LOOK); ff++) {
            if (hits(ff, GROUND_Y, SH) && hits(ff, GROUND_Y, DH)) {
              holdHits = true
              break
            }
          }
          break
        }
        if (hits(f, hY, SH)) { holdHits = true; break }
      }
      // Hold only if holding is safe and releasing isn't
      if (!holdHits) input.jump = true
    }
  }

  // ALSO in air but falling — check if we'll land on something unduckable
  if (dino.vy >= 0 && dino.y < GROUND_Y) {
    // Nothing we can do about height, but we can pre-set duck for landing
    let y = dino.y, vy = dino.vy
    for (let f = 1; f <= LOOK; f++) {
      vy += GRAVITY
      y += vy
      if (y >= GROUND_Y) {
        // Check if we need to duck immediately on landing
        for (let ff = f; ff <= Math.min(f + 5, LOOK); ff++) {
          if (hits(ff, GROUND_Y, SH) && !hits(ff, GROUND_Y, DH)) {
            input.duck = true
            break
          }
        }
        break
      }
    }
  }

  return input
}

// ---------------------------------------------------------------------------
// Game creation
// ---------------------------------------------------------------------------

export function createGame(highScore: number): GameState {
  return {
    dino: {
      x: DINO_X,
      y: GROUND_Y,
      vy: 0,
      ducking: false,
      dead: false,
      frame: 0,
    },
    obstacles: [],
    clouds: [],
    stars: generateStars(),
    ground: { offset: 0, particles: generateGroundParticles() },
    score: 0,
    highScore,
    speed: INITIAL_SPEED,
    phase: 'waiting',
    nightMode: false,
    nightTransition: 0,
    frameCount: 0,
    nextObstacleDistance: 400,
    milestoneFlash: 0,
    weather: { type: 'none', timer: 0, intensity: 0, particles: [], lightning: 0, stormClouds: [], impacts: [], windStrength: 0 },
    nextWeatherCheck: WEATHER_CHECK_INTERVAL,
    parallax: {
      biomeIndex: Math.floor(Math.random() * BIOMES.length),
      prevBiomeIndex: 0,
      transitionProgress: 1,
      farOffset: 0,
      midOffset: 0,
      nearOffset: 0,
      nextBiomeScore: BIOME_CHANGE_MIN + Math.random() * (BIOME_CHANGE_MAX - BIOME_CHANGE_MIN),
    },
    scorePopups: [],
  }
}

// Starfield extends well beyond the canvas — we see a window into it.
// Stars drift up-right so new constellations slowly come into view.
const STAR_FIELD_W = CANVAS_WIDTH * 3
const STAR_FIELD_H = (GROUND_Y - 40) * 3

function generateStars(): Star[] {
  const stars: Star[] = []
  for (let i = 0; i < 120; i++) {
    stars.push({
      x: Math.random() * STAR_FIELD_W - STAR_FIELD_W * 0.3,
      y: Math.random() * STAR_FIELD_H - STAR_FIELD_H * 0.3,
      speed: 0.4 + Math.random() * 0.6,
      size: Math.random() < 0.15 ? 3 : Math.random() < 0.35 ? 2 : 1,
    })
  }
  return stars
}

function generateGroundParticles(): GroundParticle[] {
  const particles: GroundParticle[] = []
  const groundDepth = CANVAS_HEIGHT - GROUND_Y - 4 // usable depth below ground line
  for (let i = 0; i < GROUND_PARTICLE_COUNT; i++) {
    // Distribute particles across 3 layers based on depth
    const y = 4 + Math.random() * groundDepth
    const layer = y < groundDepth * 0.33 ? 0 : y < groundDepth * 0.66 ? 1 : 2
    // Surface layer has more bright specks (~40%), deeper layers fewer (~15%)
    const brightChance = layer === 0 ? 0.4 : layer === 1 ? 0.2 : 0.15
    particles.push({
      x: Math.random() * (CANVAS_WIDTH + 200), // spread beyond canvas for seamless wrap
      y,
      size: 1 + Math.floor(Math.random() * 3), // 1–3 px
      layer,
      bright: Math.random() < brightChance,
    })
  }
  return particles
}

// ---------------------------------------------------------------------------
// Main update loop
// ---------------------------------------------------------------------------

export function update(state: GameState, input: InputState): GameState {
  if (state.phase === 'dead') return state

  // Waiting phase — start on jump
  if (state.phase === 'waiting') {
    if (input.jump) {
      return {
        ...state,
        phase: 'playing',
        dino: {
          ...state.dino,
          vy: JUMP_VELOCITY,
        },
      }
    }
    return state
  }

  // Playing phase
  let dino = { ...state.dino }
  let { speed, score, highScore, nightMode, nightTransition,
        nextObstacleDistance, milestoneFlash } = state
  let frameCount = state.frameCount + 1

  // --- Dino physics ---
  const onGround = dino.y >= GROUND_Y

  // Jump input
  if (input.jump && onGround && dino.vy >= 0) {
    dino.vy = JUMP_VELOCITY
  }

  // Variable jump height: if holding jump while rising, reduce gravity
  const effectiveGravity = (input.jump && dino.vy < 0)
    ? GRAVITY * HOLD_GRAVITY_FACTOR
    : GRAVITY

  if (!onGround || dino.vy < 0) {
    dino.vy += effectiveGravity
    dino.y += dino.vy
  }

  // Land on ground
  if (dino.y >= GROUND_Y) {
    dino.y = GROUND_Y
    dino.vy = 0
  }

  // Ducking (only on ground)
  dino.ducking = input.duck && onGround

  // Animation frame
  dino.frame = frameCount

  // --- Speed ---
  speed = Math.min(MAX_SPEED, speed + SPEED_INCREMENT)

  // Weather drag: windStrength (rolled per event) × intensity = actual drag
  const windDrag = state.weather.windStrength * state.weather.intensity
  const effectiveSpeed = speed * (1 - windDrag * 0.4) // up to 40% slowdown at max wind

  // --- Score (with weather multiplier) ---
  const weatherMult = getWeatherMultiplier(state.weather)
  const prevScore = score
  score += effectiveSpeed * 0.1 * weatherMult
  const prevMilestone = Math.floor(prevScore / MILESTONE_INTERVAL)
  const currMilestone = Math.floor(score / MILESTONE_INTERVAL)
  if (currMilestone > prevMilestone) {
    milestoneFlash = 20
  }
  if (milestoneFlash > 0) milestoneFlash--

  // High score
  if (score > highScore) highScore = score

  // --- Day/Night cycle ---
  const prevNightToggle = Math.floor(prevScore / NIGHT_TOGGLE_INTERVAL)
  const currNightToggle = Math.floor(score / NIGHT_TOGGLE_INTERVAL)
  if (currNightToggle > prevNightToggle) {
    nightMode = !nightMode
  }
  // Smooth transition
  if (nightMode && nightTransition < 1) {
    nightTransition = Math.min(1, nightTransition + 1 / NIGHT_TRANSITION_FRAMES)
  } else if (!nightMode && nightTransition > 0) {
    nightTransition = Math.max(0, nightTransition - 1 / NIGHT_TRANSITION_FRAMES)
  }

  // --- Obstacles ---
  let obstacles = state.obstacles.map(obs => ({
    ...obs,
    x: obs.x - effectiveSpeed,
    frame: obs.frame + 1,
  }))

  // Remove off-screen
  obstacles = obstacles.filter(obs => obs.x > -60)

  // Spawn new obstacles
  nextObstacleDistance -= effectiveSpeed
  if (nextObstacleDistance <= 0) {
    const type = randomObstacleType(score)
    obstacles.push({
      type,
      x: CANVAS_WIDTH + 10,
      y: getObstacleY(type),
      frame: 0,
    })
    nextObstacleDistance = randomObstacleGap(effectiveSpeed)
  }

  // --- Collision detection ---
  for (const obs of obstacles) {
    if (checkCollision(dino, obs)) {
      dino.dead = true
      return {
        ...state,
        dino,
        obstacles,
        score,
        highScore: Math.max(highScore, score),
        speed,
        phase: 'dead',
        nightMode,
        nightTransition,
        frameCount,
        nextObstacleDistance,
        milestoneFlash: 0,
        ground: { offset: (state.ground.offset + effectiveSpeed) % 12, particles: state.ground.particles },
        weather: { type: 'none', timer: 0, intensity: 0, particles: [], lightning: 0, stormClouds: [], impacts: [], windStrength: 0 },
      }
    }
  }

  // --- Obstacle clear bonuses ---
  let scorePopups = state.scorePopups
    .map(p => ({ ...p, age: p.age + 1 }))
    .filter(p => p.age < p.maxAge)
  for (const obs of obstacles) {
    if (obs.scored) continue
    const sp = getObstacleSprite(obs)
    const sz = getSpriteSize(sp)
    const ow = sz.w * PIXEL_SCALE
    if (obs.x + ow < dino.x) {
      obs.scored = true
      const bonus = Math.round((OBSTACLE_BONUS[obs.type] ?? 10) * weatherMult)
      score += bonus
      if (score > highScore) highScore = score
      scorePopups.push({
        x: obs.x + ow / 2,
        y: obs.y - sz.h * PIXEL_SCALE - 5,
        text: `+${bonus}`,
        age: 0,
        maxAge: 50,
      })
    }
  }

  // --- Clouds (density oscillates, higher clouds move faster) ---
  let clouds = state.clouds.map(c => ({
    ...c,
    x: c.x - c.speed,
  }))
  clouds = clouds.filter(c => c.x > -(60 * c.scale))
  // Compound sine waves → irregular periods: clear, scattered, overcast
  const cw1 = Math.sin(frameCount * 0.0008)
  const cw2 = Math.sin(frameCount * 0.0023 + 1.5)
  const cw3 = Math.sin(frameCount * 0.0004 + 0.7) // slow wave for occasional overcast
  const cloudPhase = Math.max(0, Math.min(1, (cw1 + cw2 + cw3 * 0.5) * 0.2 + 0.5))
  const maxClouds = Math.floor(1 + cloudPhase * 13) // 1–14 (overcast peak)
  const spawnInterval = Math.floor(30 + (1 - cloudPhase) * 270) // 30–300 frames
  if (frameCount % spawnInterval === 0 && clouds.length < maxClouds) {
    const cy = 15 + Math.random() * 65
    // Higher clouds (lower y) → closer to viewer → bigger + faster + spaced further apart
    const depthT = 1 - (cy - 15) / 65 // 1 = highest (y=15), 0 = lowest (y=80)
    const scale = 1.5 + depthT * 2     // 1.5× at bottom, 3.5× at top
    clouds.push({
      x: CANVAS_WIDTH + 20 + depthT * 60, // bigger clouds start further off-screen
      y: cy,
      speed: 0.5 + depthT * 2.5,          // higher → faster (parallax depth)
      spriteIndex: Math.floor(Math.random() * CLOUD_SPRITES.length),
      scale,
    })
  }

  // --- Ground scroll ---
  const groundOffset = (state.ground.offset + effectiveSpeed) % 12
  const wrapWidth = CANVAS_WIDTH + 200
  const groundParticles = state.ground.particles.map(p => {
    let nx = p.x - effectiveSpeed * GROUND_LAYER_SPEEDS[p.layer]
    if (nx < -10) nx += wrapWidth
    return { ...p, x: nx }
  })

  // --- Parallax ---
  const parallax = { ...state.parallax }
  parallax.farOffset += effectiveSpeed * FAR_SPEED
  parallax.midOffset += effectiveSpeed * MID_SPEED
  parallax.nearOffset += effectiveSpeed * NEAR_SPEED
  // Biome transition progress
  if (parallax.transitionProgress < 1) {
    parallax.transitionProgress = Math.min(1, parallax.transitionProgress + 1 / BIOME_TRANSITION_FRAMES)
  }
  // Biome change
  if (score >= parallax.nextBiomeScore) {
    parallax.prevBiomeIndex = parallax.biomeIndex
    let next = Math.floor(Math.random() * BIOMES.length)
    if (next === parallax.biomeIndex) next = (next + 1) % BIOMES.length
    parallax.biomeIndex = next
    parallax.transitionProgress = 0
    parallax.nextBiomeScore = score + BIOME_CHANGE_MIN + Math.random() * (BIOME_CHANGE_MAX - BIOME_CHANGE_MIN)
  }

  // --- Stars (drift up-right at ~80° from horizontal) ---
  // All stars move at the same rate — they're at infinity, no parallax
  // cos(80°) ≈ 0.174, sin(80°) ≈ 0.985
  const STAR_DRIFT = 0.04
  const stars = state.stars.map(s => {
    let nx = s.x + 0.174 * STAR_DRIFT
    let ny = s.y - 0.985 * STAR_DRIFT
    // Wrap around the extended starfield
    if (ny < -STAR_FIELD_H * 0.3) { ny += STAR_FIELD_H; nx = Math.random() * STAR_FIELD_W - STAR_FIELD_W * 0.3 }
    if (nx > STAR_FIELD_W * 0.7) { nx -= STAR_FIELD_W; ny = Math.random() * STAR_FIELD_H - STAR_FIELD_H * 0.3 }
    return { ...s, x: nx, y: ny }
  })

  // --- Weather ---
  const weatherResult = updateWeather(
    state.weather, score, nightMode, state.nextWeatherCheck,
    BIOMES[parallax.biomeIndex].name, effectiveSpeed,
  )

  return {
    ...state,
    dino,
    obstacles,
    clouds,
    stars,
    ground: { offset: groundOffset, particles: groundParticles },
    score,
    highScore,
    speed,
    phase: 'playing',
    nightMode,
    nightTransition,
    frameCount,
    nextObstacleDistance,
    milestoneFlash,
    weather: weatherResult.weather,
    nextWeatherCheck: weatherResult.nextWeatherCheck,
    parallax,
    scorePopups,
  }
}
