/**
 * Shared types for the Games Hub feature.
 */

export type Difficulty = 'easy' | 'medium' | 'hard' | 'expert'

export type GameCategory = 'puzzle' | 'strategy' | 'arcade' | 'word'

export interface GameInfo {
  id: string
  name: string
  description: string
  icon: string
  path: string
  difficulty: 'easy' | 'medium' | 'hard'
  sessionLength: string
  category: GameCategory
}

export interface GameScore {
  gameId: string
  score: number
  date: string
  difficulty?: Difficulty
  metadata?: Record<string, unknown>
}

export type GameStatus = 'idle' | 'playing' | 'won' | 'lost' | 'draw'

export type GameSortOption = 'default' | 'a-z' | 'z-a' | 'difficulty' | 'category' | 'recent'
