/**
 * Article Reader Mini Player Component
 * Persistent player that morphs between mini-bar and full modal
 * Shows word-highlighted text in expanded mode
 */

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, Minimize2, ListVideo, ExternalLink, RotateCcw, Volume2, RefreshCw } from 'lucide-react'
import { useArticleReader } from '../contexts/ArticleReaderContext'
import { sourceColors } from './news'
import { markdownToPlainText } from '../pages/news/helpers'

// Voice options for display
const VOICES: Record<string, { name: string; gender: string }> = {
  aria: { name: 'Aria', gender: 'Female' },
  guy: { name: 'Guy', gender: 'Male' },
  jenny: { name: 'Jenny', gender: 'Female' },
  brian: { name: 'Brian', gender: 'Male' },
  emma: { name: 'Emma', gender: 'Female' },
  andrew: { name: 'Andrew', gender: 'Male' },
}

// Format seconds to MM:SS
function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function ArticleReaderMiniPlayer() {
  const {
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    isExpanded,
    setExpanded,
    currentArticle,
    isLoading,
    isPaused,
    isReady,
    words,
    currentWordIndex,
    currentTime,
    duration,
    currentVoice,
    playbackRate,
    articleContent,
    articleContentLoading,
    voiceCycleEnabled,
    toggleVoiceCycle,
    nextArticle,
    previousArticle,
    closeMiniPlayer,
    playArticle,
    play,
    pause,
    resume,
    replay,
    seekToWord,
    skipWords,
    setVoice,
    setRate,
  } = useArticleReader()

  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [showSettingsDropdown, setShowSettingsDropdown] = useState(false)
  const [hoveredPlaylistIndex, setHoveredPlaylistIndex] = useState<number | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const settingsRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const wordRefs = useRef<(HTMLSpanElement | null)[]>([])

  // Convert article content to plain text for word matching
  const plainText = useMemo(() => {
    return articleContent ? markdownToPlainText(articleContent) : ''
  }, [articleContent])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
        setHoveredPlaylistIndex(null)
      }
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setShowSettingsDropdown(false)
      }
    }
    if (showPlaylistDropdown || showSettingsDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown, showSettingsDropdown])

  // Auto-scroll to keep current word visible in expanded mode
  useEffect(() => {
    if (isExpanded && currentWordIndex >= 0 && wordRefs.current[currentWordIndex] && contentRef.current) {
      const wordEl = wordRefs.current[currentWordIndex]
      const container = contentRef.current

      if (wordEl) {
        const wordRect = wordEl.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()

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
  }, [currentWordIndex, isExpanded])

  // Toggle play/pause
  const togglePlayPause = useCallback(() => {
    if (isPaused) {
      resume()
    } else if (isReady) {
      play()
    } else {
      pause()
    }
  }, [isPaused, isReady, play, pause, resume])

  // Progress bar click handler - word-based to match visual progress
  const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (words.length === 0) return

    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const percentage = clickX / rect.width

    // Calculate target word index based on percentage
    const targetIndex = Math.floor(percentage * words.length)
    const clampedIndex = Math.max(0, Math.min(targetIndex, words.length - 1))

    seekToWord(clampedIndex)
  }, [words, seekToWord])

  // Build word-highlighted content by matching TTS words to text words sequentially
  const renderedContent = useMemo(() => {
    // Show placeholder if no content yet
    if (!plainText) {
      return (
        <p className="text-slate-400 italic">
          Click the play button to load and read this article aloud.
        </p>
      )
    }

    // Show plain text if TTS hasn't loaded words yet
    if (words.length === 0) {
      return <p className="text-slate-300 leading-relaxed whitespace-pre-wrap">{plainText}</p>
    }

    // Extract all words from plain text with their positions
    // Include hyphens and apostrophes as part of words (e.g., "anti-union", "don't")
    // Note: en-dashes (–) and em-dashes (—) are treated as separators since TTS reads them as separate words
    const textWords: Array<{ start: number; end: number; text: string; lower: string }> = []
    const wordRegex = /[a-zA-Z0-9]+(?:[-''][a-zA-Z0-9]+)*/g
    let match
    while ((match = wordRegex.exec(plainText)) !== null) {
      textWords.push({
        start: match.index,
        end: match.index + match[0].length,
        text: match[0],
        lower: match[0].toLowerCase(),
      })
    }

    // Match TTS words to text words sequentially
    // Each TTS word maps to the next matching text word
    const ttsToTextMap = new Map<number, number>() // TTS index -> text word index
    let textWordPtr = 0

    words.forEach((word, ttsIndex) => {
      // Get alphanumeric lowercase version of TTS word
      const ttsWordClean = word.text.toLowerCase().replace(/[^a-z0-9]/g, '')
      if (ttsWordClean.length === 0) return // Skip punctuation-only words

      // Search for matching text word starting from current pointer
      for (let i = textWordPtr; i < textWords.length; i++) {
        const textWordClean = textWords[i].lower.replace(/[^a-z0-9]/g, '')

        // Check if they match (exact or one contains the other for contractions/possessives)
        if (textWordClean === ttsWordClean ||
            textWordClean.includes(ttsWordClean) ||
            ttsWordClean.includes(textWordClean)) {
          ttsToTextMap.set(ttsIndex, i)
          textWordPtr = i + 1 // Move pointer past this word
          break
        }
      }
    })

    // Build the rendered content
    const elements: React.ReactElement[] = []
    let lastEnd = 0

    // Create reverse map: text word index -> TTS index
    const textToTTSMap = new Map<number, number>()
    ttsToTextMap.forEach((textIdx, ttsIdx) => {
      textToTTSMap.set(textIdx, ttsIdx)
    })

    textWords.forEach((tw, twIndex) => {
      // Add any text before this word (punctuation, spaces, etc.)
      if (tw.start > lastEnd) {
        elements.push(
          <span key={`between-${twIndex}`} className="text-slate-300">
            {plainText.slice(lastEnd, tw.start)}
          </span>
        )
      }

      const ttsWordIndex = textToTTSMap.get(twIndex)
      const isCurrentWord = ttsWordIndex !== undefined && ttsWordIndex === currentWordIndex

      elements.push(
        <span
          key={`word-${twIndex}`}
          ref={(el) => {
            if (ttsWordIndex !== undefined) {
              wordRefs.current[ttsWordIndex] = el
            }
          }}
          onClick={() => {
            if (ttsWordIndex !== undefined) {
              seekToWord(ttsWordIndex)
            }
          }}
          className={`transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50 ${
            isCurrentWord
              ? 'bg-yellow-500/40 text-white font-medium'
              : 'text-slate-300'
          }`}
        >
          {tw.text}
        </span>
      )

      lastEnd = tw.end
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

  // Don't render if not showing
  if (!isPlaying || !showMiniPlayer || !currentArticle) {
    return null
  }

  const voiceInfo = VOICES[currentVoice] || { name: currentVoice, gender: '' }
  const isAudioActive = !isLoading && (isPaused || words.length > 0)

  return (
    <>
      {/* Dark overlay when expanded */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-black/80 z-40 transition-opacity"
          onClick={() => setExpanded(false)}
        />
      )}

      {/* Player container - morphs between mini-bar and modal */}
      <div
        className={`fixed z-50 transition-all duration-300 ease-in-out ${
          isExpanded
            ? 'inset-4 sm:inset-8 md:inset-12 lg:inset-x-[10%] lg:inset-y-8'
            : 'bottom-0 left-0 right-0 h-20'
        }`}
      >
        <div className={`h-full bg-slate-800 shadow-2xl flex transition-all duration-300 ${
          isExpanded
            ? 'flex-col rounded-lg border border-slate-700'
            : 'flex-row border-t border-slate-700'
        }`}>

          {/* Expanded: Full article view */}
          {isExpanded && (
            <div
              ref={contentRef}
              className="flex-1 overflow-y-auto"
            >
              {/* Full-size thumbnail */}
              {currentArticle.thumbnail && (
                <div className="w-full bg-slate-900">
                  <img
                    src={currentArticle.thumbnail}
                    alt=""
                    className="w-full h-auto max-h-[400px] object-contain mx-auto"
                    onError={(e) => {
                      (e.target as HTMLImageElement).parentElement!.style.display = 'none'
                    }}
                  />
                </div>
              )}

              {/* Article content */}
              <div className="p-6">
                {/* Header with source, time, voice */}
                <div className="flex flex-wrap items-center gap-3 mb-4">
                  <span className={`px-2 py-1 rounded text-sm font-medium border ${
                    sourceColors[currentArticle.source] || 'bg-slate-600 text-slate-300'
                  }`}>
                    {currentArticle.source_name}
                  </span>
                  {currentArticle.published && (
                    <span className="text-sm text-slate-400">
                      {new Date(currentArticle.published).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  )}
                  <span className="text-sm text-green-400">
                    Voice: {voiceInfo.name} ({voiceInfo.gender})
                  </span>
                  <span className="text-sm text-slate-500">
                    Article {currentIndex + 1} of {playlist.length}
                  </span>
                </div>

                {/* Title */}
                <h1 className="text-2xl font-bold text-white mb-6 leading-tight">
                  {currentArticle.title}
                </h1>

                {/* Article content with word highlighting */}
                <div className="prose prose-invert prose-slate max-w-none">
                  {articleContentLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="animate-spin w-8 h-8 border-2 border-green-500 border-t-transparent rounded-full" />
                      <span className="ml-3 text-slate-400">Loading article content...</span>
                    </div>
                  ) : (
                    renderedContent
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Mini mode: Thumbnail */}
          {!isExpanded && currentArticle.thumbnail && (
            <div className="w-28 h-16 my-auto ml-4 rounded overflow-hidden flex-shrink-0 bg-slate-900">
              <img
                src={currentArticle.thumbnail}
                alt=""
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            </div>
          )}

          {/* Controls bar */}
          <div className={`flex transition-all duration-300 ${
            isExpanded
              ? 'flex-row items-center gap-4 p-4 border-t border-slate-700'
              : 'flex-col flex-1 px-4 py-2 justify-center gap-1'
          }`}>
            {/* Article info */}
            <div className={`min-w-0 ${isExpanded ? 'flex-shrink-0 w-64' : 'flex items-center gap-2'}`}>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium border flex-shrink-0 ${
                sourceColors[currentArticle.source] || 'bg-slate-600 text-slate-300'
              }`}>
                {currentArticle.source_name}
              </span>
              <h4 className={`text-sm font-medium text-white truncate ${isExpanded ? 'mt-1' : 'flex-1'}`}>
                {currentArticle.title}
              </h4>
              <div className="flex items-center gap-2 text-xs text-slate-500 flex-shrink-0">
                <span>{voiceInfo.name}</span>
                <span>{currentIndex + 1}/{playlist.length}</span>
              </div>
            </div>

            {/* Progress and controls */}
            <div className={`flex items-center gap-2 ${isExpanded ? 'flex-1' : ''}`}>
              {/* Progress bar and time */}
              <div className="flex-1 flex items-center gap-2 min-w-0">
                <span className="text-xs text-slate-400 w-10 text-right flex-shrink-0 font-mono">
                  {formatTime(currentTime)}
                </span>

                <div
                  className="flex-1 h-2 bg-slate-700 rounded-full cursor-pointer group relative"
                  onClick={handleProgressClick}
                >
                  <div
                    className="h-full bg-green-500 rounded-full transition-all duration-100 relative"
                    style={{ width: words.length > 0 ? `${((currentWordIndex + 1) / words.length) * 100}%` : '0%' }}
                  >
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>

                <span className="text-xs text-slate-400 w-12 flex-shrink-0 font-mono">
                  -{formatTime(Math.max(0, duration - currentTime))}
                </span>
              </div>

              {/* Playback controls */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {/* Replay */}
                <button
                  onClick={replay}
                  disabled={!isAudioActive}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Restart"
                >
                  <RotateCcw className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Skip back 10 words */}
                <button
                  onClick={() => skipWords(-10)}
                  disabled={!isAudioActive}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Back 10 words"
                >
                  <SkipBack className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Play/Pause */}
                <button
                  onClick={togglePlayPause}
                  disabled={isLoading}
                  className={`flex items-center justify-center rounded-full bg-green-600 hover:bg-green-500 disabled:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-12 h-12' : 'w-9 h-9'}`}
                  title={isPaused || isReady ? "Play" : "Pause"}
                >
                  {isLoading ? (
                    <div className={`animate-spin border-2 border-white border-t-transparent rounded-full ${isExpanded ? 'w-6 h-6' : 'w-4 h-4'}`} />
                  ) : isPaused || isReady ? (
                    <Play className={`${isExpanded ? 'w-6 h-6' : 'w-4 h-4'} ml-0.5`} fill="white" />
                  ) : (
                    <Pause className={isExpanded ? 'w-6 h-6' : 'w-4 h-4'} />
                  )}
                </button>

                {/* Skip forward 10 words */}
                <button
                  onClick={() => skipWords(10)}
                  disabled={!isAudioActive}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Forward 10 words"
                >
                  <SkipForward className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Previous article */}
                <button
                  onClick={previousArticle}
                  disabled={currentIndex === 0}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Previous article"
                >
                  <SkipBack className={`${isExpanded ? 'w-5 h-5' : 'w-4 h-4'}`} />
                  <SkipBack className={`${isExpanded ? 'w-5 h-5' : 'w-4 h-4'} -ml-3`} />
                </button>

                {/* Next article */}
                <button
                  onClick={nextArticle}
                  disabled={currentIndex >= playlist.length - 1}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Next article"
                >
                  <SkipForward className={`${isExpanded ? 'w-5 h-5' : 'w-4 h-4'}`} />
                  <SkipForward className={`${isExpanded ? 'w-5 h-5' : 'w-4 h-4'} -ml-3`} />
                </button>
              </div>

              {/* Secondary controls */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {/* Settings dropdown (voice, speed) */}
                <div className="relative" ref={settingsRef}>
                  <button
                    onClick={() => setShowSettingsDropdown(!showSettingsDropdown)}
                    className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                    title="Settings"
                  >
                    <Volume2 className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  </button>

                  {showSettingsDropdown && (
                    <div className="fixed bottom-24 right-20 w-64 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-[60] p-4">
                      <div className="space-y-4">
                        {/* Voice cycling toggle */}
                        <div>
                          <button
                            onClick={toggleVoiceCycle}
                            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors ${
                              voiceCycleEnabled
                                ? 'bg-green-500/20 border border-green-500/30 text-green-400'
                                : 'bg-slate-700 border border-slate-600 text-slate-400'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <RefreshCw className={`w-4 h-4 ${voiceCycleEnabled ? 'animate-spin' : ''}`} style={{ animationDuration: '3s' }} />
                              <span className="text-sm font-medium">Voice Cycling</span>
                            </div>
                            <span className="text-xs">{voiceCycleEnabled ? 'ON' : 'OFF'}</span>
                          </button>
                          <p className="text-xs text-slate-500 mt-1">
                            {voiceCycleEnabled
                              ? 'Different voice for each article'
                              : 'Same voice for all articles'}
                          </p>
                        </div>

                        {/* Voice selector */}
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Voice</label>
                          <select
                            value={currentVoice}
                            onChange={(e) => setVoice(e.target.value)}
                            disabled={voiceCycleEnabled || (!isPaused && !isReady)}
                            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-white disabled:opacity-50"
                          >
                            {Object.entries(VOICES).map(([id, v]) => (
                              <option key={id} value={id}>
                                {v.name} ({v.gender})
                              </option>
                            ))}
                          </select>
                          <p className="text-xs text-slate-500 mt-1">
                            {voiceCycleEnabled
                              ? 'Disable cycling to choose voice'
                              : 'Change voice while paused'}
                          </p>
                        </div>

                        {/* Speed selector */}
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Speed</label>
                          <select
                            value={playbackRate}
                            onChange={(e) => setRate(parseFloat(e.target.value))}
                            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-white"
                          >
                            <option value="0.75">0.75x</option>
                            <option value="1">1x</option>
                            <option value="1.25">1.25x</option>
                            <option value="1.5">1.5x</option>
                            <option value="2">2x</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Playlist dropdown */}
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setShowPlaylistDropdown(!showPlaylistDropdown)}
                    className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                    title="Playlist"
                  >
                    <ListVideo className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  </button>

                  {showPlaylistDropdown && (
                    <div className="fixed bottom-24 right-4 w-80 max-h-96 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-[60]">
                      <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                        <p className="text-xs text-slate-400">Reading queue ({playlist.length} articles)</p>
                      </div>
                      {playlist.map((article, idx) => (
                        <button
                          key={`playlist-${article.url}`}
                          onClick={() => {
                            playArticle(idx)
                            setShowPlaylistDropdown(false)
                          }}
                          onMouseEnter={() => setHoveredPlaylistIndex(idx)}
                          onMouseLeave={() => setHoveredPlaylistIndex(null)}
                          className={`w-full flex items-start gap-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                            idx === currentIndex ? 'bg-green-500/10 border-l-2 border-green-500' : ''
                          } ${hoveredPlaylistIndex === idx ? 'bg-blue-500/10' : ''}`}
                        >
                          <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                            idx === currentIndex ? 'bg-green-500 text-white' : hoveredPlaylistIndex === idx ? 'bg-blue-500 text-white' : 'bg-slate-600 text-slate-300'
                          }`}>
                            {idx + 1}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-white truncate">{article.title}</p>
                            <p className="text-xs text-slate-500">{article.source_name}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Open article in new tab */}
                {isExpanded && (
                  <a
                    href={currentArticle.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                    title="Open on website"
                  >
                    <ExternalLink className="w-5 h-5" />
                  </a>
                )}

                {/* Expand/Minimize */}
                <button
                  onClick={() => setExpanded(!isExpanded)}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title={isExpanded ? "Minimize" : "Expand"}
                >
                  {isExpanded ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-4 h-4" />}
                </button>

                {/* Close */}
                <button
                  onClick={closeMiniPlayer}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-red-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Close"
                >
                  <X className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Spacer to prevent content from being hidden behind mini-player */}
      {!isExpanded && <div className="h-20" />}
    </>
  )
}
