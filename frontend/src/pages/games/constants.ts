/**
 * Game registry and shared constants for the Games Hub.
 */

import {
  Grid3X3,
  CircleDot,
  Hash,
  Bomb,
  PenLine,
  LetterText,
  Waypoints,
  LayoutGrid,
  Layers,
  Grip,
  Table2,
  Crown,
  Triangle,
  FlipHorizontal,
  Spade,
  Dices,
  ChessKnight,
} from 'lucide-react'
import type { ComponentType } from 'react'
import type { GameInfo } from './types'

export const GAMES: GameInfo[] = [
  {
    id: 'tic-tac-toe',
    name: 'Tic-Tac-Toe',
    description: 'Classic 3x3 strategy',
    icon: 'Grid3X3',
    path: '/games/tic-tac-toe',
    difficulty: 'easy',
    sessionLength: '1-2 min',
    category: 'strategy',
  },
  {
    id: 'connect-four',
    name: 'Connect Four',
    description: 'Drop discs, line up four',
    icon: 'CircleDot',
    path: '/games/connect-four',
    difficulty: 'medium',
    sessionLength: '3-5 min',
    category: 'strategy',
  },
  {
    id: '2048',
    name: '2048',
    description: 'Slide and merge to 2048',
    icon: 'Hash',
    path: '/games/2048',
    difficulty: 'medium',
    sessionLength: '5-15 min',
    category: 'puzzle',
  },
  {
    id: 'minesweeper',
    name: 'Minesweeper',
    description: 'Clear the minefield',
    icon: 'Bomb',
    path: '/games/minesweeper',
    difficulty: 'medium',
    sessionLength: '3-15 min',
    category: 'puzzle',
  },
  {
    id: 'hangman',
    name: 'Hangman',
    description: 'Guess the word before time runs out',
    icon: 'PenLine',
    path: '/games/hangman',
    difficulty: 'easy',
    sessionLength: '2-5 min',
    category: 'word',
  },
  {
    id: 'sudoku',
    name: 'Sudoku',
    description: 'Fill the 9x9 grid with logic',
    icon: 'Table2',
    path: '/games/sudoku',
    difficulty: 'medium',
    sessionLength: '5-20 min',
    category: 'puzzle',
  },
  {
    id: 'wordle',
    name: 'Wordle',
    description: 'Guess the daily 5-letter word',
    icon: 'LetterText',
    path: '/games/wordle',
    difficulty: 'medium',
    sessionLength: '5-10 min',
    category: 'word',
  },
  {
    id: 'snake',
    name: 'Snake',
    description: 'Eat, grow, survive',
    icon: 'Waypoints',
    path: '/games/snake',
    difficulty: 'easy',
    sessionLength: '2-10 min',
    category: 'arcade',
  },
  {
    id: 'ultimate-tic-tac-toe',
    name: 'Ultimate Tic-Tac-Toe',
    description: 'Tic-tac-toe inception',
    icon: 'LayoutGrid',
    path: '/games/ultimate-tic-tac-toe',
    difficulty: 'hard',
    sessionLength: '10-20 min',
    category: 'strategy',
  },
  {
    id: 'mahjong',
    name: 'Mahjong Solitaire',
    description: 'Match tiles to clear the board',
    icon: 'Layers',
    path: '/games/mahjong',
    difficulty: 'hard',
    sessionLength: '10-20 min',
    category: 'puzzle',
  },
  {
    id: 'nonogram',
    name: 'Nonogram',
    description: 'Solve clues to reveal pixel art',
    icon: 'Grip',
    path: '/games/nonogram',
    difficulty: 'medium',
    sessionLength: '10-20 min',
    category: 'puzzle',
  },
  {
    id: 'checkers',
    name: 'Checkers',
    description: 'Classic board game vs AI',
    icon: 'Crown',
    path: '/games/checkers',
    difficulty: 'medium',
    sessionLength: '10-20 min',
    category: 'strategy',
  },
  {
    id: 'plinko',
    name: 'Plinko',
    description: 'Drop balls for multipliers',
    icon: 'Triangle',
    path: '/games/plinko',
    difficulty: 'easy',
    sessionLength: '2-5 min',
    category: 'arcade',
  },
  {
    id: 'memory',
    name: 'Memory',
    description: 'Flip cards to find matching pairs',
    icon: 'FlipHorizontal',
    path: '/games/memory',
    difficulty: 'easy',
    sessionLength: '2-5 min',
    category: 'puzzle',
  },
  {
    id: 'solitaire',
    name: 'Solitaire',
    description: 'Classic Klondike card game',
    icon: 'Spade',
    path: '/games/solitaire',
    difficulty: 'medium',
    sessionLength: '10-20 min',
    category: 'strategy',
  },
  {
    id: 'backgammon',
    name: 'Backgammon',
    description: 'Classic dice board game vs AI',
    icon: 'Dices',
    path: '/games/backgammon',
    difficulty: 'hard',
    sessionLength: '15-30 min',
    category: 'strategy',
  },
  {
    id: 'chess',
    name: 'Chess',
    description: 'The ultimate strategy game vs AI',
    icon: 'ChessKnight',
    path: '/games/chess',
    difficulty: 'hard',
    sessionLength: '10-30 min',
    category: 'strategy',
  },
]

/** Icon component map — maps icon string names to actual Lucide components */
export const GAME_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  Grid3X3,
  CircleDot,
  Hash,
  Bomb,
  PenLine,
  Table2,
  LetterText,
  Waypoints,
  LayoutGrid,
  Layers,
  Grip,
  Crown,
  Triangle,
  FlipHorizontal,
  Spade,
  Dices,
  ChessKnight,
}

/** Category filter options for the hub page */
export const GAME_CATEGORIES = [
  { value: 'all', label: 'All' },
  { value: 'puzzle', label: 'Puzzle' },
  { value: 'strategy', label: 'Strategy' },
  { value: 'word', label: 'Word' },
  { value: 'arcade', label: 'Arcade' },
] as const

/** Sort options for the hub page */
export const SORT_OPTIONS = [
  { value: 'default', label: 'Default' },
  { value: 'a-z', label: 'A \u2192 Z' },
  { value: 'z-a', label: 'Z \u2192 A' },
  { value: 'difficulty', label: 'Difficulty' },
  { value: 'category', label: 'Category' },
  { value: 'recent', label: 'Recently Played' },
] as const

/** Get the current user's ID from stored auth data (returns 0 if not logged in). */
function getStoredUserId(): number {
  try {
    const raw = localStorage.getItem('auth_user')
    if (raw) {
      const user = JSON.parse(raw)
      return user.id || 0
    }
  } catch { /* ignore */ }
  return 0
}

/** localStorage key prefix for all game data — scoped to the current user. */
export function getStoragePrefix(): string {
  return `zenith-games-u${getStoredUserId()}-`
}

/**
 * @deprecated Use getStoragePrefix() for user-scoped keys.
 * Kept as fallback for static import contexts.
 */
export const STORAGE_PREFIX = 'zenith-games-'
