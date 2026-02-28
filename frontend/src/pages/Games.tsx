/**
 * Games page — router entry point for the Games Hub.
 *
 * Lazy-loaded from App.tsx. Uses nested Routes so each game
 * gets its own sub-route (e.g., /games/sudoku, /games/snake).
 * Individual games are lazy-loaded for code splitting.
 */

import { Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { GameHub } from './games/components/GameHub'

// Games will be lazy-loaded here as they are built in subsequent phases.
// Phase 0 only has the hub — individual game routes are added in Phases 1-3.

export default function Games() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-[300px]">
        <LoadingSpinner size="lg" text="Loading game..." />
      </div>
    }>
      <Routes>
        <Route index element={<GameHub />} />
        {/* Game routes will be added here as games are built */}
      </Routes>
    </Suspense>
  )
}
