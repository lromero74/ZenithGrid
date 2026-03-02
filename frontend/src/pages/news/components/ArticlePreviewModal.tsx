/**
 * Article Preview Modal Component
 *
 * Full-screen modal for previewing articles with optional reader mode and TTS.
 */

import { X, ExternalLink, BookOpen, AlertCircle } from 'lucide-react'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { formatRelativeTime } from '../../../components/news'
import { NewsItem, CATEGORY_COLORS, ArticleContentResponse } from '../../../types/newsTypes'
import { ArticleContent } from './ArticleContent'
import { TTSControls } from './TTSControls'
import type { UseTTSSyncReturn } from '../../../hooks/useTTSSync'

interface ArticlePreviewModalProps {
  previewArticle: NewsItem
  readerModeEnabled: boolean
  setReaderModeEnabled: (enabled: boolean) => void
  articleContent: ArticleContentResponse | null
  articleContentLoading: boolean
  articlePlainText: string
  tts: UseTTSSyncReturn
  onClose: () => void
}

export function ArticlePreviewModal({
  previewArticle,
  readerModeEnabled,
  setReaderModeEnabled,
  articleContent,
  articleContentLoading,
  articlePlainText,
  tts,
  onClose,
}: ArticlePreviewModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className={`bg-slate-800 rounded-lg w-full max-h-[90vh] overflow-hidden shadow-2xl transition-all duration-300 ${
          readerModeEnabled ? 'max-w-4xl' : 'max-w-2xl'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header with reader mode toggle */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2">
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium border ${
                CATEGORY_COLORS[previewArticle.category] || 'bg-slate-600 text-slate-300 border-slate-500'
              }`}
            >
              {previewArticle.source_name}
            </span>
            {previewArticle.published && (
              <span className="text-xs text-slate-500">
                {formatRelativeTime(previewArticle.published)}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-2">
            {/* Reader Mode Toggle */}
            <button
              onClick={() => setReaderModeEnabled(!readerModeEnabled)}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                readerModeEnabled
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : 'bg-slate-700 text-slate-400 hover:text-white hover:bg-slate-600'
              }`}
              title="Toggle reader mode to fetch and display full article content"
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">Reader Mode</span>
            </button>
            <button
              onClick={onClose}
              className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
            >
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Modal content */}
        <div className="overflow-y-auto max-h-[calc(90vh-140px)]">
          {/* Full-size thumbnail - always show if available */}
          {previewArticle.thumbnail && (
            <div className="w-full aspect-video bg-slate-900">
              <img
                src={previewArticle.thumbnail}
                alt=""
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            </div>
          )}

          <div className="p-6 space-y-4">
            {/* Title - use extracted title in reader mode if available */}
            <h2 className="text-xl font-bold text-white leading-tight">
              {readerModeEnabled && articleContent?.title ? articleContent.title : previewArticle.title}
            </h2>

            {/* Author and date in reader mode */}
            {readerModeEnabled && articleContent?.success && (articleContent.author || articleContent.date) && (
              <div className="flex items-center space-x-3 text-sm text-slate-400">
                {articleContent.author && <span>By {articleContent.author}</span>}
                {articleContent.author && articleContent.date && <span>•</span>}
                {articleContent.date && <span>{articleContent.date}</span>}
              </div>
            )}

            {/* Reader Mode Content */}
            {readerModeEnabled ? (
              <>
                {/* Loading state */}
                {articleContentLoading && (
                  <div className="flex flex-col items-center justify-center py-12 space-y-4">
                    <LoadingSpinner size="md" text="Fetching article content..." />
                    <p className="text-sm text-slate-500">
                      Extracting readable content from the source
                    </p>
                  </div>
                )}

                {/* Error state */}
                {articleContent && !articleContent.success && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                    <div className="flex items-start space-x-3">
                      <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-red-400 font-medium">Unable to extract article content</p>
                        <p className="text-sm text-red-400/70 mt-1">{articleContent.error}</p>
                        <p className="text-sm text-slate-400 mt-3">
                          Try opening the full article on the source website instead.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Success - Full article content with word highlighting */}
                {articleContent?.success && articleContent.content && (
                  <ArticleContent
                    content={articleContent.content}
                    words={tts.words}
                    currentWordIndex={tts.currentWordIndex}
                    onSeekToWord={tts.seekToWord}
                  />
                )}
              </>
            ) : (
              <>
                {/* Default preview mode - summary only */}
                {previewArticle.summary && (
                  <p className="text-slate-300 leading-relaxed">
                    {previewArticle.summary}
                  </p>
                )}

                {/* No summary message */}
                {!previewArticle.summary && (
                  <p className="text-slate-500 italic">
                    No summary available. Enable Reader Mode or click below to read the full article.
                  </p>
                )}

                {/* Hint to enable reader mode */}
                <div className="bg-slate-700/50 rounded-lg p-4 mt-4">
                  <div className="flex items-start space-x-3">
                    <BookOpen className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-slate-300 font-medium">Want to read the full article here?</p>
                      <p className="text-sm text-slate-400 mt-1">
                        Enable <span className="text-blue-400">Reader Mode</span> above to extract and display the full article content in a clean, readable format.
                      </p>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Modal footer with TTS controls and actions */}
        <div className="p-4 border-t border-slate-700">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Left side: Close + TTS Controls */}
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
              >
                Close
              </button>

              {/* TTS Controls - only show when reader mode is active with content */}
              {readerModeEnabled && articleContent?.success && articleContent.content && (
                <TTSControls
                  isLoading={tts.isLoading}
                  isPlaying={tts.isPlaying}
                  isPaused={tts.isPaused}
                  isReady={tts.isReady}
                  error={tts.error}
                  currentTime={tts.currentTime}
                  duration={tts.duration}
                  currentVoice={tts.currentVoice}
                  playbackRate={tts.playbackRate}
                  onLoadAndPlay={() => tts.loadAndPlay(articlePlainText)}
                  onPlay={tts.play}
                  onPause={tts.pause}
                  onResume={tts.resume}
                  onStop={tts.stop}
                  onReplay={tts.replay}
                  onSkipWords={tts.skipWords}
                  onSetVoice={tts.setVoice}
                  onSetRate={tts.setRate}
                />
              )}
            </div>

            {/* Right side: Read on Website button */}
            <a
              href={previewArticle.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-medium transition-colors flex-shrink-0"
            >
              <ExternalLink className="w-4 h-4" />
              <span className="hidden sm:inline">Read on Website</span>
              <span className="sm:hidden">Website</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
