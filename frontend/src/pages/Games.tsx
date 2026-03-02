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

// Phase 5: Card & Board Games
const Memory = lazy(() => import('./games/components/games/memory/Memory'))
const Solitaire = lazy(() => import('./games/components/games/solitaire/Solitaire'))
const Backgammon = lazy(() => import('./games/components/games/backgammon/Backgammon'))
const Chess = lazy(() => import('./games/components/games/chess/Chess'))

// Phase 6: Card Games
const Blackjack = lazy(() => import('./games/components/games/blackjack/Blackjack'))
const VideoPoker = lazy(() => import('./games/components/games/video-poker/VideoPoker'))
const Hearts = lazy(() => import('./games/components/games/hearts/Hearts'))
const Spades = lazy(() => import('./games/components/games/spades/Spades'))
const CrazyEights = lazy(() => import('./games/components/games/crazy-eights/CrazyEights'))
const GinRummy = lazy(() => import('./games/components/games/gin-rummy/GinRummy'))
const Freecell = lazy(() => import('./games/components/games/freecell/Freecell'))

// Phase 7: Arcade Games
const Centipede = lazy(() => import('./games/components/games/centipede/Centipede'))
const SpaceInvaders = lazy(() => import('./games/components/games/space-invaders/SpaceInvaders'))

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
        {/* Phase 5: Card & Board Games */}
        <Route path="memory" element={<Memory />} />
        <Route path="solitaire" element={<Solitaire />} />
        <Route path="backgammon" element={<Backgammon />} />
        <Route path="chess" element={<Chess />} />
        {/* Phase 6: Card Games */}
        <Route path="blackjack" element={<Blackjack />} />
        <Route path="video-poker" element={<VideoPoker />} />
        <Route path="hearts" element={<Hearts />} />
        <Route path="spades" element={<Spades />} />
        <Route path="crazy-eights" element={<CrazyEights />} />
        <Route path="gin-rummy" element={<GinRummy />} />
        <Route path="freecell" element={<Freecell />} />
        {/* Phase 7: Arcade Games */}
        <Route path="centipede" element={<Centipede />} />
        <Route path="space-invaders" element={<SpaceInvaders />} />
      </Routes>
    </Suspense>
  )
}
