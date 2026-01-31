/**
 * Article Content Component
 * Displays article text with karaoke-style word highlighting during TTS playback
 * Auto-scrolls to keep the current word visible
 */

import React, { useEffect, useRef, useMemo } from 'react'
import { WordTiming } from '../hooks/useTTSSync'
import { markdownToPlainText } from '../helpers'

interface ArticleContentProps {
  content: string  // Markdown content
  words: WordTiming[]
  currentWordIndex: number
  onSeekToWord: (index: number) => void
}

export function ArticleContent({
  content,
  words,
  currentWordIndex,
  onSeekToWord,
}: ArticleContentProps) {
  const wordRefs = useRef<(HTMLSpanElement | null)[]>([])
  const lastScrolledIndex = useRef(-1)

  // Convert markdown to plain text
  const plainText = useMemo(() => markdownToPlainText(content), [content])

  // Auto-scroll to keep current word visible
  useEffect(() => {
    if (currentWordIndex >= 0 && wordRefs.current[currentWordIndex]) {
      // Only scroll if we've moved to a new word (avoid constant scrolling)
      if (Math.abs(currentWordIndex - lastScrolledIndex.current) > 3) {
        const wordEl = wordRefs.current[currentWordIndex]
        if (wordEl) {
          wordEl.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          })
          lastScrolledIndex.current = currentWordIndex
        }
      }
    }
  }, [currentWordIndex])

  // Build word-wrapped text from TTS words
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
              onClick={() => onSeekToWord(wordIndex)}
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
  }, [words, plainText, currentWordIndex, onSeekToWord])

  return (
    <div className="prose prose-invert prose-slate max-w-none">
      {renderedContent}
    </div>
  )
}
