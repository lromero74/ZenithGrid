/**
 * Synced Article Reader Component
 * Displays article text with karaoke-style word highlighting during TTS playback
 * Auto-scrolls to keep the current word visible
 */

import React, { useEffect, useRef, useMemo } from 'react'
import { Play, Pause, Square, Loader2, Volume2, RotateCcw, SkipBack, SkipForward } from 'lucide-react'
import { useTTSSync } from '../hooks/useTTSSync'
import { markdownToPlainText } from '../helpers'
import { TTS_VOICES } from '../../../constants/voices'

interface SyncedArticleReaderProps {
  content: string  // Markdown content
  onClose?: () => void
}

export function SyncedArticleReader({ content, onClose: _onClose }: SyncedArticleReaderProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const wordRefs = useRef<(HTMLSpanElement | null)[]>([])

  const {
    isLoading,
    isPlaying,
    isPaused,
    isReady,
    error,
    words,
    currentWordIndex,
    currentTime,
    duration,
    currentVoice,
    playbackRate,
    loadAndPlay,
    play,
    pause,
    resume,
    stop,
    replay,
    seekToWord,
    skipWords,
    setVoice,
    setRate,
  } = useTTSSync()

  // Number of words to skip with back/forward buttons
  const SKIP_WORD_COUNT = 10

  // Convert markdown to plain text for TTS
  const plainText = useMemo(() => markdownToPlainText(content), [content])

  // Auto-scroll to keep current word visible
  useEffect(() => {
    if (currentWordIndex >= 0 && wordRefs.current[currentWordIndex] && containerRef.current) {
      const wordEl = wordRefs.current[currentWordIndex]
      const container = containerRef.current

      if (wordEl) {
        const wordRect = wordEl.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()

        // Check if word is outside visible area
        const isAbove = wordRect.top < containerRect.top + 50
        const isBelow = wordRect.bottom > containerRect.bottom - 50

        if (isAbove || isBelow) {
          wordEl.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          })
        }
      }
    }
  }, [currentWordIndex])

  // Stop playback when component unmounts
  useEffect(() => {
    return () => {
      stop()
    }
  }, [stop])

  // Build word-wrapped text from TTS words
  // We need to match words to the plain text to preserve spacing/punctuation
  const renderedContent = useMemo(() => {
    if (words.length === 0) {
      // Not loaded yet, show plain text
      return <p className="text-slate-300 leading-relaxed whitespace-pre-wrap">{plainText}</p>
    }

    // Build spans for each word with proper spacing
    const elements: React.ReactElement[] = []
    let lastEnd = 0
    let textPointer = 0

    words.forEach((word, index) => {
      // Find this word in the plain text
      const wordLower = word.text.toLowerCase()
      let searchStart = textPointer

      // Search for the word in the remaining text
      while (searchStart < plainText.length) {
        const foundIndex = plainText.toLowerCase().indexOf(wordLower, searchStart)
        if (foundIndex === -1) break

        // Check if it's a word boundary
        const charBefore = foundIndex > 0 ? plainText[foundIndex - 1] : ' '
        const charAfter = foundIndex + word.text.length < plainText.length
          ? plainText[foundIndex + word.text.length]
          : ' '

        const isWordBoundary = /[\s\n.,!?;:'"()\-—]/.test(charBefore) || foundIndex === 0
        const isWordEnd = /[\s\n.,!?;:'"()\-—]/.test(charAfter) || foundIndex + word.text.length === plainText.length

        if (isWordBoundary && isWordEnd) {
          // Add any text before this word (spaces, punctuation)
          if (foundIndex > lastEnd) {
            const between = plainText.slice(lastEnd, foundIndex)
            elements.push(
              <span key={`between-${index}`} className="text-slate-300">
                {between}
              </span>
            )
          }

          // Add the word with highlighting capability and click-to-seek
          const isCurrentWord = index === currentWordIndex
          const wordIndex = index  // Capture index for closure
          elements.push(
            <span
              key={`word-${index}`}
              ref={(el) => { wordRefs.current[index] = el }}
              onClick={() => seekToWord(wordIndex)}
              className={`transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50 ${
                isCurrentWord
                  ? 'bg-yellow-500/40 text-white font-medium'
                  : 'text-slate-300'
              }`}
            >
              {plainText.slice(foundIndex, foundIndex + word.text.length)}
            </span>
          )

          lastEnd = foundIndex + word.text.length
          textPointer = lastEnd
          break
        }
        searchStart = foundIndex + 1
      }
    })

    // Add any remaining text after the last word
    if (lastEnd < plainText.length) {
      elements.push(
        <span key="remaining" className="text-slate-300">
          {plainText.slice(lastEnd)}
        </span>
      )
    }

    return <p className="leading-relaxed whitespace-pre-wrap">{elements}</p>
  }, [words, plainText, currentWordIndex, seekToWord])

  // Format time as mm:ss
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-slate-700/50 rounded-lg border border-slate-600 mb-4">
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
                onClick={replay}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title="Restart"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => skipWords(-SKIP_WORD_COUNT)}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title={`Back ${SKIP_WORD_COUNT} words`}
              >
                <SkipBack className="w-4 h-4" />
              </button>
              <button
                onClick={pause}
                className="flex items-center space-x-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg text-white transition-colors"
              >
                <Pause className="w-4 h-4" />
                <span>Pause</span>
              </button>
              <button
                onClick={() => skipWords(SKIP_WORD_COUNT)}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title={`Forward ${SKIP_WORD_COUNT} words`}
              >
                <SkipForward className="w-4 h-4" />
              </button>
              <button
                onClick={stop}
                className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
                title="Stop"
              >
                <Square className="w-4 h-4" />
              </button>
            </>
          ) : isPaused ? (
            <>
              <button
                onClick={replay}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title="Restart"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => skipWords(-SKIP_WORD_COUNT)}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title={`Back ${SKIP_WORD_COUNT} words`}
              >
                <SkipBack className="w-4 h-4" />
              </button>
              <button
                onClick={resume}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-white transition-colors"
              >
                <Play className="w-4 h-4" />
                <span>Resume</span>
              </button>
              <button
                onClick={() => skipWords(SKIP_WORD_COUNT)}
                className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white transition-colors"
                title={`Forward ${SKIP_WORD_COUNT} words`}
              >
                <SkipForward className="w-4 h-4" />
              </button>
              <button
                onClick={stop}
                className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
                title="Stop"
              >
                <Square className="w-4 h-4" />
              </button>
            </>
          ) : isReady ? (
            <>
              <button
                onClick={play}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white transition-colors animate-pulse"
              >
                <Play className="w-4 h-4" />
                <span>Click to Start</span>
              </button>
              <button
                onClick={stop}
                className="p-2 bg-red-600 hover:bg-red-500 rounded-lg text-white transition-colors"
                title="Cancel"
              >
                <Square className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button
              onClick={() => loadAndPlay(plainText)}
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
            onChange={(e) => setVoice(e.target.value)}
            disabled={isPlaying || isPaused}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-white disabled:opacity-50"
          >
            {TTS_VOICES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.gender}, {v.locale})
              </option>
            ))}
          </select>
        </div>

        {/* Speed control */}
        <div className="flex items-center space-x-2">
          <label className="text-xs text-slate-400">Speed:</label>
          <select
            value={playbackRate}
            onChange={(e) => setRate(parseFloat(e.target.value))}
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

      {/* Scrollable content with word highlighting */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto prose prose-invert prose-slate max-w-none pr-2"
        style={{ maxHeight: 'calc(100% - 80px)' }}
      >
        {renderedContent}
      </div>
    </div>
  )
}
