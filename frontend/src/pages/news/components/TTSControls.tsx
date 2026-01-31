/**
 * TTS Control Bar Component
 * Playback controls for text-to-speech with word highlighting
 */

import { Play, Pause, Square, Loader2, Volume2, RotateCcw, SkipBack, SkipForward } from 'lucide-react'

// Voice options
const VOICES = [
  { id: 'aria', name: 'Aria', gender: 'Female' },
  { id: 'guy', name: 'Guy', gender: 'Male' },
  { id: 'jenny', name: 'Jenny', gender: 'Female' },
  { id: 'brian', name: 'Brian', gender: 'Male' },
  { id: 'emma', name: 'Emma', gender: 'Female' },
  { id: 'andrew', name: 'Andrew', gender: 'Male' },
]

// Number of words to skip with back/forward buttons
const SKIP_WORD_COUNT = 10

interface TTSControlsProps {
  isLoading: boolean
  isPlaying: boolean
  isPaused: boolean
  isReady: boolean
  error: string | null
  currentTime: number
  duration: number
  currentVoice: string
  playbackRate: number
  onLoadAndPlay: () => void
  onPlay: () => void
  onPause: () => void
  onResume: () => void
  onStop: () => void
  onReplay: () => void
  onSkipWords: (count: number) => void
  onSetVoice: (voice: string) => void
  onSetRate: (rate: number) => void
}

export function TTSControls({
  isLoading,
  isPlaying,
  isPaused,
  isReady,
  error,
  currentTime,
  duration,
  currentVoice,
  playbackRate,
  onLoadAndPlay,
  onPlay,
  onPause,
  onResume,
  onStop,
  onReplay,
  onSkipWords,
  onSetVoice,
  onSetRate,
}: TTSControlsProps) {
  // Format time as mm:ss
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Play/Pause/Stop buttons */}
      <div className="flex items-center space-x-2">
        {isLoading ? (
          <button
            disabled
            className="flex items-center space-x-2 px-4 py-2 bg-slate-600 rounded-lg text-slate-400"
          >
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Loading...</span>
          </button>
        ) : isPlaying ? (
          <>
            <button
              onClick={onReplay}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title="Restart"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={() => onSkipWords(-SKIP_WORD_COUNT)}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title={`Back ${SKIP_WORD_COUNT} words`}
            >
              <SkipBack className="w-4 h-4" />
            </button>
            <button
              onClick={onPause}
              className="flex items-center space-x-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg text-white transition-colors"
            >
              <Pause className="w-4 h-4" />
              <span>Pause</span>
            </button>
            <button
              onClick={() => onSkipWords(SKIP_WORD_COUNT)}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title={`Forward ${SKIP_WORD_COUNT} words`}
            >
              <SkipForward className="w-4 h-4" />
            </button>
            <button
              onClick={onStop}
              className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
              title="Stop"
            >
              <Square className="w-4 h-4" />
            </button>
          </>
        ) : isPaused ? (
          <>
            <button
              onClick={onReplay}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title="Restart"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={() => onSkipWords(-SKIP_WORD_COUNT)}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title={`Back ${SKIP_WORD_COUNT} words`}
            >
              <SkipBack className="w-4 h-4" />
            </button>
            <button
              onClick={onResume}
              className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-white transition-colors"
            >
              <Play className="w-4 h-4" />
              <span>Resume</span>
            </button>
            <button
              onClick={() => onSkipWords(SKIP_WORD_COUNT)}
              className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
              title={`Forward ${SKIP_WORD_COUNT} words`}
            >
              <SkipForward className="w-4 h-4" />
            </button>
            <button
              onClick={onStop}
              className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
              title="Stop"
            >
              <Square className="w-4 h-4" />
            </button>
          </>
        ) : isReady ? (
          <>
            <button
              onClick={onPlay}
              className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white transition-colors animate-pulse"
            >
              <Play className="w-4 h-4" />
              <span>Click to Start</span>
            </button>
            <button
              onClick={onStop}
              className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
              title="Cancel"
            >
              <Square className="w-4 h-4" />
            </button>
          </>
        ) : (
          <button
            onClick={onLoadAndPlay}
            className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-white transition-colors"
          >
            <Volume2 className="w-4 h-4" />
            <span>Read Aloud</span>
          </button>
        )}
      </div>

      {/* Progress indicator */}
      {(isPlaying || isPaused) && duration > 0 && (
        <div className="flex items-center space-x-2 text-xs text-slate-400">
          <span>{formatTime(currentTime)}</span>
          <div className="w-24 h-1.5 bg-slate-600 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 transition-all duration-100"
              style={{ width: `${(currentTime / duration) * 100}%` }}
            />
          </div>
          <span>{formatTime(duration)}</span>
        </div>
      )}

      {/* Voice selector */}
      <div className="flex items-center space-x-2">
        <label className="text-xs text-slate-400">Voice:</label>
        <select
          value={currentVoice}
          onChange={(e) => onSetVoice(e.target.value)}
          disabled={isPlaying || isPaused}
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-white disabled:opacity-50"
        >
          {VOICES.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.gender})
            </option>
          ))}
        </select>
      </div>

      {/* Speed control */}
      <div className="flex items-center space-x-2">
        <label className="text-xs text-slate-400">Speed:</label>
        <select
          value={playbackRate}
          onChange={(e) => onSetRate(parseFloat(e.target.value))}
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-white"
        >
          <option value="0.75">0.75x</option>
          <option value="1">1x</option>
          <option value="1.25">1.25x</option>
          <option value="1.5">1.5x</option>
          <option value="2">2x</option>
        </select>
      </div>

      {/* Error display */}
      {error && (
        <span className="text-xs text-red-400">{error}</span>
      )}
    </div>
  )
}
