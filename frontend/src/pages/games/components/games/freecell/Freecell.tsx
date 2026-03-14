/**
 * Freecell — all cards face-up solitaire variant.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CARD_SIZE_NARROW } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getSuitSymbol, type Suit } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  dealFreecell,
  moveToFreecell,
  moveFromFreecell,
  moveTableauToFoundation,
  moveTableauStack,
  checkWin,
  getHint,
  type FreecellState,
  type FreecellHint,
} from './freecellEngine'

interface SavedState {
  gameState: FreecellState
  gameStatus: GameStatus
}

interface Selection {
  type: 'tableau' | 'freecell'
  colOrCell: number
  cardIndex?: number
}

// ── Help modal ───────────────────────────────────────────────────────

function FreecellHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Freecell</h2>

        {/* Goal */}
        <Sec title="Goal">
          Move all <B>52 cards</B> to the four foundation piles, building each
          suit up from Ace to King. Unlike most solitaire variants, every card
          is dealt face-up, so the game is entirely about strategy rather than
          luck.
        </Sec>

        {/* Layout */}
        <Sec title="Layout">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>8 tableau columns</B> &mdash; all 52 cards are dealt face-up
              across these columns (the first 4 columns receive 7 cards each,
              the remaining 4 receive 6 cards each).</Li>
            <Li><B>4 free cells</B> (top-left) &mdash; temporary storage slots.
              Each free cell can hold exactly <B>one card</B> at a time.</Li>
            <Li><B>4 foundations</B> (top-right) &mdash; one per suit. Build each
              foundation up from <B>Ace through King</B> in the same suit.</Li>
          </ul>
        </Sec>

        {/* Tableau Rules */}
        <Sec title="Tableau Rules">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Cards on the tableau are stacked in <B>descending rank</B> with
              <B> alternating colors</B> (e.g., a red 6 can be placed on a
              black 7).</Li>
            <Li>Any card or valid sequence can be moved to an <B>empty column</B>.</Li>
            <Li>You can move a <B>stack of cards</B> as a group if they form a
              valid descending, alternating-color sequence &mdash; but only if
              there are enough empty free cells and empty columns to
              theoretically perform the move one card at a time.</Li>
          </ul>
        </Sec>

        {/* Supermove */}
        <Sec title="Supermove (Stack Moves)">
          The number of cards you can move at once depends on available
          empty spaces:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Formula: <B>(empty free cells + 1) x 2^(empty columns)</B>.</Li>
            <Li>With <B>0</B> empty free cells and <B>0</B> empty columns, you
              can only move <B>1</B> card at a time.</Li>
            <Li>With <B>2</B> empty free cells and <B>1</B> empty column, you
              can move up to <B>6</B> cards at once.</Li>
            <Li>With all <B>4</B> free cells empty and <B>1</B> empty column,
              you can move up to <B>10</B> cards.</Li>
          </ul>
        </Sec>

        {/* Foundation Rules */}
        <Sec title="Foundation Rules">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Each foundation accepts cards of a <B>single suit</B>, starting
              with the <B>Ace</B> and building up in order to <B>King</B>.</Li>
            <Li>Cards can be moved to a foundation from the <B>tableau</B> or
              from a <B>free cell</B>.</Li>
            <Li><B>Double-click</B> a tableau card to automatically send it to
              the matching foundation (if the move is valid).</Li>
          </ul>
        </Sec>

        {/* Free Cells */}
        <Sec title="Free Cells">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Each free cell holds <B>one card</B>. Use them as temporary
              storage to unblock cards underneath.</Li>
            <Li>A card in a free cell can be moved to a <B>tableau column</B>
              (following the descending/alternating rule) or directly to a
              <B> foundation</B>.</Li>
            <Li>Free cells are a <B>limited resource</B> &mdash; filling them
              all restricts your ability to move stacks.</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li><B>Click</B> a card to select it (highlighted in yellow).</li>
            <li><B>Click</B> a destination (column, free cell, or foundation)
              to move the selected card there.</li>
            <li>To move a <B>stack</B>, click the topmost card of the sequence
              you want to move, then click the destination column.</li>
            <li><B>Double-click</B> the bottom card of a tableau column to
              auto-send it to the foundation.</li>
            <li>Click a selected card again or click an invalid destination to
              <B> deselect</B>.</li>
          </ol>
        </Sec>

        {/* Tools */}
        <Sec title="Tools">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Undo</B> &mdash; take back your last move (one level).</Li>
            <Li><B>Hint</B> &mdash; highlights a suggested move. Priority order:
              tableau-to-foundation, freecell-to-foundation, tableau-to-tableau,
              then card-to-freecell.</Li>
            <Li><B>New Game</B> &mdash; deal a fresh game at any time.</Li>
          </ul>
        </Sec>

        {/* Winning */}
        <Sec title="Winning">
          The game is won when all <B>4 foundations</B> are complete (13 cards
          each, Ace through King). Your score is the total number of
          <B> moves</B> used &mdash; fewer moves means a better game.
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Keep free cells open.</B> Every occupied free cell reduces
              the number of cards you can move as a stack.</Li>
            <Li><B>Empty columns are powerful.</B> An empty column doubles your
              supermove capacity &mdash; try to free up at least one early.</Li>
            <Li><B>Build foundations evenly.</B> Don&apos;t rush one suit ahead
              of the others &mdash; you may need those lower cards on the
              tableau for sequencing.</Li>
            <Li><B>Plan ahead.</B> Since all cards are visible, look several
              moves ahead before committing to a path.</Li>
            <Li><B>Uncover Aces and 2s first.</B> Getting low cards to the
              foundations early frees up space and opens options.</Li>
            <Li><B>Avoid filling all free cells.</B> If all 4 are occupied and
              no empty columns exist, you can only move one card at a time,
              which often leads to a dead end.</Li>
          </ul>
        </Sec>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
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

// ── Component ────────────────────────────────────────────────────────

const FOUNDATION_SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

function FreecellSinglePlayer({ onGameEnd }: {
  onGameEnd?: (result: 'win' | 'loss' | 'draw', moveCount?: number) => void
} = {}) {
  const { load, save, clear } = useGameState<SavedState>('freecell')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('freecell'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('freecell')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<FreecellState>(
    () => saved?.gameState ?? dealFreecell()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [undoStack, setUndoStack] = useState<FreecellState[]>([])
  // activeHint used to highlight hint targets when Hint button pressed
  const [, setActiveHint] = useState<FreecellHint | null>(null)

  useEffect(() => {
    if (gameStatus !== 'won') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (checkWin(gameState)) {
      sfx.play('win')
      setGameStatus('won')
      setSelection(null)
      clear()
      onGameEnd?.('win', gameState.moves)
    }
  }, [gameState, clear, onGameEnd])

  useEffect(() => { setActiveHint(null) }, [gameState])

  const pushUndo = useCallback((state: FreecellState) => {
    setUndoStack([state])
  }, [])

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    setGameState(undoStack[0])
    setUndoStack([])
    setSelection(null)
  }, [undoStack])

  const handleHintClick = useCallback(() => {
    if (gameStatus !== 'playing') return
    const hint = getHint(gameState)
    if (hint) {
      setActiveHint(hint)
      setSelection(null)
    }
  }, [gameState, gameStatus])

  const handleNewGame = useCallback(() => {
    setGameState(dealFreecell())
    setGameStatus('playing')
    setSelection(null)
    setUndoStack([])
    setActiveHint(null)
    clear()
  }, [clear])

  // Click on a freecell slot
  const handleFreecellClick = useCallback((cellIdx: number) => {
    if (gameStatus !== 'playing') return
    const card = gameState.freecells[cellIdx]

    if (selection) {
      // Try to move selected to this freecell (only if empty)
      if (!card && selection.type === 'tableau') {
        const result = moveToFreecell(gameState, selection.colOrCell)
        if (result) {
          pushUndo(gameState)
          sfx.play('place')
          setGameState(result)
        }
      } else if (card && !selection) {
        // Select this freecell card
        setSelection({ type: 'freecell', colOrCell: cellIdx })
        return
      }
      setSelection(null)
      return
    }

    if (card) {
      sfx.play('pickup')
      setSelection({ type: 'freecell', colOrCell: cellIdx })
    }
  }, [gameState, gameStatus, selection, pushUndo])

  // Click on a foundation slot
  const handleFoundationClick = useCallback((fIdx: number) => {
    if (gameStatus !== 'playing' || !selection) return

    if (selection.type === 'freecell') {
      const result = moveFromFreecell(gameState, selection.colOrCell, 'foundation', fIdx)
      if (result) {
        pushUndo(gameState)
        sfx.play('place')
        setGameState(result)
      }
    } else if (selection.type === 'tableau') {
      const result = moveTableauToFoundation(gameState, selection.colOrCell)
      if (result) {
        pushUndo(gameState)
        sfx.play('place')
        setGameState(result)
      }
    }
    setSelection(null)
  }, [gameState, gameStatus, selection, pushUndo])

  // Click on tableau column/card
  const handleTableauClick = useCallback((colIdx: number, cardIdx?: number) => {
    if (gameStatus !== 'playing') return
    music.init()
    sfx.init()
    music.start()
    const col = gameState.tableau[colIdx]

    if (selection) {
      // Try to move selected cards here
      if (selection.type === 'freecell') {
        const result = moveFromFreecell(gameState, selection.colOrCell, 'tableau', colIdx)
        if (result) {
          pushUndo(gameState)
          sfx.play('place')
          setGameState(result)
          setSelection(null)
          return
        }
      } else if (selection.type === 'tableau') {
        const srcIdx = selection.cardIndex ?? (gameState.tableau[selection.colOrCell].length - 1)
        const result = moveTableauStack(gameState, selection.colOrCell, srcIdx, colIdx)
        if (result) {
          pushUndo(gameState)
          sfx.play('place')
          setGameState(result)
          setSelection(null)
          return
        }
      }

      // If click is on a card in this column, re-select
      if (cardIdx !== undefined && col[cardIdx]) {
        setSelection({ type: 'tableau', colOrCell: colIdx, cardIndex: cardIdx })
        return
      }
      setSelection(null)
      return
    }

    // Nothing selected — select this card
    if (cardIdx !== undefined && col[cardIdx]) {
      sfx.play('pickup')
      setSelection({ type: 'tableau', colOrCell: colIdx, cardIndex: cardIdx })
    }
  }, [gameState, gameStatus, selection, pushUndo])

  // Double-click on tableau card → try foundation
  const handleTableauDoubleClick = useCallback((colIdx: number) => {
    if (gameStatus !== 'playing') return
    const result = moveTableauToFoundation(gameState, colIdx)
    if (result) {
      pushUndo(gameState)
      sfx.play('place')
      setGameState(result)
      setSelection(null)
    }
  }, [gameState, gameStatus, pushUndo])

  const isSelected = useCallback((type: 'tableau' | 'freecell', colOrCell: number, cardIdx?: number) => {
    if (!selection || selection.type !== type || selection.colOrCell !== colOrCell) return false
    if (type === 'freecell') return true
    if (cardIdx === undefined) return false
    return cardIdx >= (selection.cardIndex ?? gameState.tableau[selection.colOrCell].length - 1)
  }, [selection, gameState])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button onClick={handleUndo} disabled={undoStack.length === 0}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          Undo
        </button>
        <button onClick={handleHintClick} disabled={gameStatus !== 'playing'}
          className="px-3 py-1.5 text-xs rounded bg-emerald-700 text-emerald-100 hover:bg-emerald-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          Hint
        </button>
        <button onClick={handleNewGame}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
          New Game
        </button>
      </div>
      <span className="text-xs text-slate-400">Moves: {gameState.moves}</span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Freecell" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-xl space-y-3">
        {/* Top row: Free cells | Foundations */}
        <div className="flex w-full justify-between gap-1">
          {/* Free cells */}
          <div className="flex gap-1 sm:gap-2">
            {gameState.freecells.map((card, i) => (
              <div
                key={`fc-${i}`}
                onClick={() => handleFreecellClick(i)}
                className={`${CARD_SIZE_NARROW} rounded-md border border-dashed border-slate-600/50 cursor-pointer ${
                  isSelected('freecell', i) ? 'ring-2 ring-yellow-400' : ''
                }`}
              >
                {card && <CardFace card={card} selected={isSelected('freecell', i)} />}
              </div>
            ))}
          </div>

          {/* Foundations */}
          <div className="flex gap-1 sm:gap-2">
            {FOUNDATION_SUITS.map((suit, f) => (
              <div
                key={suit}
                onClick={() => handleFoundationClick(f)}
                className={`${CARD_SIZE_NARROW} rounded-md border border-dashed border-slate-600/50 cursor-pointer`}
              >
                {gameState.foundations[f].length > 0 ? (
                  <CardFace card={gameState.foundations[f][gameState.foundations[f].length - 1]} />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className={`text-lg opacity-20 ${suit === 'hearts' || suit === 'diamonds' ? 'text-red-400' : 'text-slate-400'}`}>
                      {getSuitSymbol(suit)}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Tableau — 8 columns */}
        <div className="flex w-full gap-1 sm:gap-1.5">
          {gameState.tableau.map((col, colIdx) => (
            <div
              key={colIdx}
              className="flex-1 relative min-h-[5.5rem] sm:min-h-[6.5rem]"
              onClick={() => col.length === 0 && handleTableauClick(colIdx)}
            >
              {col.length === 0 && (
                <div className="absolute inset-x-0 top-0 h-[4.25rem] sm:h-[5.625rem] rounded-md border border-dashed border-slate-600/30" />
              )}
              {col.map((card, cardIdx) => (
                <div
                  key={cardIdx}
                  className="absolute left-0 right-0 h-[4.25rem] sm:h-[5.625rem]"
                  style={{ top: `${cardIdx * (window.innerWidth < 640 ? 16 : 22)}px` }}
                  onClick={(e) => { e.stopPropagation(); handleTableauClick(colIdx, cardIdx) }}
                  onDoubleClick={(e) => { e.stopPropagation(); handleTableauDoubleClick(colIdx) }}
                >
                  <CardFace card={card} selected={isSelected('tableau', colIdx, cardIdx)} />
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Spacer */}
        <div style={{ minHeight: `${Math.max(...gameState.tableau.map(c => c.length)) * (window.innerWidth < 640 ? 16 : 22) + 80}px` }} />

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={gameState.moves}
            message={`Completed in ${gameState.moves} moves`}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {showHelp && <FreecellHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper ──────────────────────────────────────────────────

function FreecellRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState: _broadcastState, reportScore, reportFinish, leaveRoom } =
    useRaceMode(roomId, 'first_to_win')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', moveCount?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportScore(moveCount ?? 0)
    reportFinish(result === 'draw' ? 'loss' : result, moveCount)
  }, [reportScore, reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        localScore={localScore}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <FreecellSinglePlayer onGameEnd={handleGameEnd} />
    </div>
  )
}

export default function Freecell() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'freecell',
        gameName: 'Freecell',
        modes: ['first_to_win'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { first_to_win: 'First to complete wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <FreecellSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <FreecellRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
