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
const Crossword = lazy(() => import('./games/components/games/crossword/Crossword'))
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

// Phase 8: New Card Games
const War = lazy(() => import('./games/components/games/war/War'))
const GoFish = lazy(() => import('./games/components/games/go-fish/GoFish'))
const Rummy500 = lazy(() => import('./games/components/games/rummy-500/Rummy500'))
const Cribbage = lazy(() => import('./games/components/games/cribbage/Cribbage'))
const Euchre = lazy(() => import('./games/components/games/euchre/Euchre'))
const TexasHoldem = lazy(() => import('./games/components/games/texas-holdem/TexasHoldem'))
const Bridge = lazy(() => import('./games/components/games/bridge/Bridge'))
const Canasta = lazy(() => import('./games/components/games/canasta/Canasta'))
const Speed = lazy(() => import('./games/components/games/speed/Speed'))
const Spoons = lazy(() => import('./games/components/games/spoons/Spoons'))
const Shalas = lazy(() => import('./games/components/games/shalas/Shalas'))

// Phase 7: Arcade Games
const Centipede = lazy(() => import('./games/components/games/centipede/Centipede'))
const SpaceInvaders = lazy(() => import('./games/components/games/space-invaders/SpaceInvaders'))
const LodeRunner = lazy(() => import('./games/components/games/lode-runner/LodeRunner'))
const DinoRunner = lazy(() => import('./games/components/games/dino-runner/DinoRunner'))

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
        <Route path="crossword" element={<Crossword />} />
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
        {/* Phase 8: New Card Games */}
        <Route path="war" element={<War />} />
        <Route path="go-fish" element={<GoFish />} />
        <Route path="speed" element={<Speed />} />
        <Route path="spoons" element={<Spoons />} />
        <Route path="rummy-500" element={<Rummy500 />} />
        <Route path="cribbage" element={<Cribbage />} />
        <Route path="euchre" element={<Euchre />} />
        <Route path="texas-holdem" element={<TexasHoldem />} />
        <Route path="bridge" element={<Bridge />} />
        <Route path="canasta" element={<Canasta />} />
        <Route path="shalas" element={<Shalas />} />
        {/* Phase 7: Arcade Games */}
        <Route path="centipede" element={<Centipede />} />
        <Route path="space-invaders" element={<SpaceInvaders />} />
        <Route path="lode-runner" element={<LodeRunner />} />
        <Route path="dino-runner" element={<DinoRunner />} />
      </Routes>
    </Suspense>
  )
}
