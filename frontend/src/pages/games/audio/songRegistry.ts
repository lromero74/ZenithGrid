/**
 * Song Registry — maps every game to a unique song via genre + seed.
 *
 * Songs are lazily generated and cached. The Dino Runner keeps its
 * hand-crafted song; all others use the song factory.
 */

import type { Song } from './songTypes'
import { generateSong } from './songFactory'
import { dinoRunnerSong } from './songs/dinoRunnerSong'

// ---------------------------------------------------------------------------
// Game → Genre + Seed assignments
// ---------------------------------------------------------------------------

interface SongAssignment {
  genre: string
  seed: number
  title?: string
}

/**
 * Each game mapped to a genre and deterministic seed.
 * Same seed + genre = same song every time = no randomness on reload.
 */
const GAME_SONGS: Record<string, SongAssignment> = {
  // ---- Strategy ----
  'chess':                { genre: 'classical',  seed: 1001, title: 'Royal Gambit' },
  'checkers':             { genre: 'jazz',       seed: 1002, title: 'Checkerboard Swing' },
  'connect-four':         { genre: 'lofi',       seed: 1003, title: 'Four in a Row' },
  'tic-tac-toe':          { genre: 'chiptune',   seed: 1004, title: 'X Marks the Bit' },
  'ultimate-tic-tac-toe': { genre: 'edm',        seed: 1005, title: 'Ultimate Grid' },
  'backgammon':           { genre: 'arabic',     seed: 1006, title: 'Desert Dice' },

  // ---- Puzzle ----
  '2048':                 { genre: 'edm',        seed: 2001, title: 'Merge Force' },
  'minesweeper':          { genre: 'ambient',    seed: 2002, title: 'Minefield Haze' },
  'sudoku':               { genre: 'japanese',   seed: 2003, title: 'Nine Harmonies' },
  'mahjong':              { genre: 'japanese',    seed: 2004, title: 'Tile Garden' },
  'nonogram':             { genre: 'ambient',    seed: 2005, title: 'Pixel Reveal' },
  'memory':               { genre: 'ambient',    seed: 2006, title: 'Matching Minds' },

  // ---- Word ----
  'hangman':              { genre: 'blues',      seed: 3001, title: 'Last Letter Blues' },
  'wordle':               { genre: 'lofi',       seed: 3002, title: 'Five Letter Chill' },

  // ---- Arcade ----
  'snake':                { genre: 'chiptune',   seed: 4001, title: 'Serpent Circuit' },
  'plinko':               { genre: 'disco',      seed: 4002, title: 'Drop Zone Fever' },
  'centipede':            { genre: 'chiptune',   seed: 4003, title: 'Bug Zapper 8-Bit' },
  'space-invaders':       { genre: 'synthwave',  seed: 4004, title: 'Cosmic Defense' },
  'lode-runner':          { genre: 'rock',       seed: 4005, title: 'Gold Rush' },
  // dino-runner: uses hand-crafted song (not in this map)

  // ---- Cards: Solitaire ----
  'solitaire':            { genre: 'lofi',       seed: 5001, title: 'Klondike Calm' },
  'freecell':             { genre: 'bossanova',  seed: 5002, title: 'Free Cell Sway' },

  // ---- Cards: Trick-Taking ----
  'hearts':               { genre: 'jazz',       seed: 5101, title: 'Heartbreak Ballad' },
  'spades':               { genre: 'funk',       seed: 5102, title: 'Spade Groove' },
  'euchre':               { genre: 'celtic',     seed: 5103, title: 'Bower Reel' },
  'bridge':               { genre: 'classical',  seed: 5104, title: 'Grand Slam Suite' },

  // ---- Cards: Rummy ----
  'gin-rummy':            { genre: 'blues',      seed: 5201, title: 'Gin Joint' },
  'rummy-500':            { genre: 'jazz',       seed: 5202, title: '500 Points of Cool' },
  'canasta':              { genre: 'latin',      seed: 5203, title: 'Canasta Caliente' },

  // ---- Cards: Casino ----
  'blackjack':            { genre: 'jazz',       seed: 5301, title: 'Twenty-One Smooth' },
  'video-poker':          { genre: 'synthwave',  seed: 5302, title: 'Neon Cards' },
  'texas-holdem':         { genre: 'cinematic',  seed: 5303, title: 'All In' },

  // ---- Cards: Classic ----
  'crazy-eights':         { genre: 'reggae',     seed: 5401, title: 'Eight is Enough' },
  'war':                  { genre: 'rock',       seed: 5402, title: 'Battle Anthem' },
  'go-fish':              { genre: 'chiptune',   seed: 5403, title: 'Fish Pond Pixels' },
  'cribbage':             { genre: 'celtic',     seed: 5404, title: 'Pegging Jig' },
  'speed':                { genre: 'edm',        seed: 5405, title: 'Lightning Hands' },
  'spoons':               { genre: 'funk',       seed: 5406, title: 'Spoon Scramble' },
}

/**
 * 10 bonus genre showcase songs (not tied to specific games).
 * Useful for a "music jukebox" feature or testing all genres.
 */
const BONUS_SONGS: SongAssignment[] = [
  { genre: 'metal',       seed: 9001, title: 'Iron Grid' },
  { genre: 'electronic',  seed: 9002, title: 'Digital Frontier' },
  { genre: 'cinematic',   seed: 9003, title: 'Epic Ascent' },
  { genre: 'arabic',      seed: 9004, title: 'Silk Road' },
  { genre: 'funk',        seed: 9005, title: 'Groove Machine' },
  { genre: 'reggae',      seed: 9006, title: 'Island Breeze' },
  { genre: 'celtic',      seed: 9007, title: 'Highland Quest' },
  { genre: 'bossanova',   seed: 9008, title: 'Rio Sunset' },
  { genre: 'disco',       seed: 9009, title: 'Mirror Ball' },
  { genre: 'latin',       seed: 9010, title: 'Fuego Rhythm' },
]

// ---------------------------------------------------------------------------
// Song cache & public API
// ---------------------------------------------------------------------------

const songCache = new Map<string, Song>()

/**
 * Get the song for a game by its ID. Returns the same Song instance on
 * every call (lazy-generated, cached). The Dino Runner returns its
 * hand-crafted song.
 */
export function getSongForGame(gameId: string): Song {
  // Dino Runner keeps its hand-crafted song
  if (gameId === 'dino-runner') return dinoRunnerSong

  const cached = songCache.get(gameId)
  if (cached) return cached

  const assignment = GAME_SONGS[gameId]
  if (!assignment) {
    // Unknown game — generate a default chiptune song using the gameId as seed
    const fallbackSeed = hashString(gameId)
    const song = generateSong('chiptune', fallbackSeed, { title: `Game: ${gameId}` })
    songCache.set(gameId, song)
    return song
  }

  const song = generateSong(assignment.genre, assignment.seed, { title: assignment.title })
  songCache.set(gameId, song)
  return song
}

/**
 * Get a bonus genre showcase song by index (0-9).
 */
export function getBonusSong(index: number): Song {
  const key = `__bonus_${index}`
  const cached = songCache.get(key)
  if (cached) return cached

  const assignment = BONUS_SONGS[index % BONUS_SONGS.length]
  const song = generateSong(assignment.genre, assignment.seed, { title: assignment.title })
  songCache.set(key, song)
  return song
}

/**
 * Get the genre assignment for a game (for display purposes).
 */
export function getGameGenre(gameId: string): string | undefined {
  if (gameId === 'dino-runner') return 'synthwave'
  return GAME_SONGS[gameId]?.genre
}

/**
 * Get all game IDs that have song assignments.
 */
export function getAssignedGameIds(): string[] {
  return ['dino-runner', ...Object.keys(GAME_SONGS)]
}

/**
 * Clear the song cache (useful for testing).
 */
export function clearSongCache(): void {
  songCache.clear()
}

/** Simple string hash to number for fallback seeds. */
function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash | 0 // Convert to 32-bit integer
  }
  return Math.abs(hash)
}

/** Total number of unique songs: games + bonus. */
export const TOTAL_SONGS = Object.keys(GAME_SONGS).length + 1 + BONUS_SONGS.length // +1 for dino-runner
