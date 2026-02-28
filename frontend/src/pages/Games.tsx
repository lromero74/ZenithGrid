/**
 * Games page — router entry point for the Games Hub.
 *
 * Lazy-loaded from App.tsx. Uses nested Routes so each game
 * gets its own sub-route (e.g., /games/sudoku, /games/snake).
 * Individual games are lazy-loaded for code splitting.
 */

import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { GameHub } from './games/components/GameHub'

// Phase 1: Easy Games
const TicTacToe = lazy(() => import('./games/components/games/tic-tac-toe/TicTacToe'))
const Hangman = lazy(() => import('./games/components/games/hangman/Hangman'))
const Snake = lazy(() => import('./games/components/games/snake/Snake'))

// Phase 2: Medium Games
const TwentyFortyEight = lazy(() => import('./games/components/games/twenty-forty-eight/TwentyFortyEight'))
const ConnectFour = lazy(() => import('./games/components/games/connect-four/ConnectFour'))
const Minesweeper = lazy(() => import('./games/components/games/minesweeper/Minesweeper'))
const Wordle = lazy(() => import('./games/components/games/wordle/Wordle'))
const Nonogram = lazy(() => import('./games/components/games/nonogram/Nonogram'))

// Phase 3: Hard Games
const Sudoku = lazy(() => import('./games/components/games/sudoku/Sudoku'))
const UltimateTicTacToe = lazy(() => import('./games/components/games/ultimate-tic-tac-toe/UltimateTicTacToe'))
const Mahjong = lazy(() => import('./games/components/games/mahjong/Mahjong'))

// Phase 4: New Games
const Checkers = lazy(() => import('./games/components/games/checkers/Checkers'))
const Plinko = lazy(() => import('./games/components/games/plinko/Plinko'))

export default function Games() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-[300px]">
        <LoadingSpinner size="lg" text="Loading game..." />
      </div>
    }>
      <Routes>
        <Route index element={<GameHub />} />
        {/* Phase 1: Easy Games */}
        <Route path="tic-tac-toe" element={<TicTacToe />} />
        <Route path="hangman" element={<Hangman />} />
        <Route path="snake" element={<Snake />} />
        {/* Phase 2: Medium Games */}
        <Route path="2048" element={<TwentyFortyEight />} />
        <Route path="connect-four" element={<ConnectFour />} />
        <Route path="minesweeper" element={<Minesweeper />} />
        <Route path="wordle" element={<Wordle />} />
        <Route path="nonogram" element={<Nonogram />} />
        {/* Phase 3: Hard Games */}
        <Route path="sudoku" element={<Sudoku />} />
        <Route path="ultimate-tic-tac-toe" element={<UltimateTicTacToe />} />
        <Route path="mahjong" element={<Mahjong />} />
        {/* Phase 4: New Games */}
        <Route path="checkers" element={<Checkers />} />
        <Route path="plinko" element={<Plinko />} />
      </Routes>
    </Suspense>
  )
}
