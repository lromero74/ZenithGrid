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
  const prevHighlightRef = useRef<number>(-1)
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

  // O(1) word highlighting via direct DOM manipulation (P2)
  useEffect(() => {
    const prev = prevHighlightRef.current
    if (prev >= 0 && wordRefs.current[prev]) {
      const el = wordRefs.current[prev]!
      el.classList.remove('bg-yellow-500/40', 'text-white', 'font-medium')
      el.classList.add('text-slate-300')
    }
    if (currentWordIndex >= 0 && wordRefs.current[currentWordIndex]) {
      const el = wordRefs.current[currentWordIndex]!
      el.classList.remove('text-slate-300')
      el.classList.add('bg-yellow-500/40', 'text-white', 'font-medium')
    }
    prevHighlightRef.current = currentWordIndex
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

    // Helper to check if character is a word boundary (any non-alphanumeric character)
    const isWordBoundaryChar = (char: string) => !/[a-zA-Z0-9]/.test(char)

    // Helper to normalize text for matching (handle smart quotes)
    const normalizeForMatch = (text: string) => text.toLowerCase().replace(/['']/g, "'").replace(/[""]/g, '"')

    words.forEach((word, index) => {
      const wordNormalized = normalizeForMatch(word.text)
      let searchStart = textPointer
      let found = false

      // Strategy 1: Try exact match with word boundaries
      while (searchStart < plainText.length && !found) {
        const foundIndex = normalizeForMatch(plainText).indexOf(wordNormalized, searchStart)
        if (foundIndex === -1) break

        const charBefore = foundIndex > 0 ? plainText[foundIndex - 1] : ' '
        const charAfter = foundIndex + word.text.length < plainText.length
          ? plainText[foundIndex + word.text.length]
          : ' '

        const isWordStart = isWordBoundaryChar(charBefore) || foundIndex === 0
        const isWordEnd = isWordBoundaryChar(charAfter) || foundIndex + word.text.length === plainText.length

        if (isWordStart && isWordEnd) {
          if (foundIndex > lastEnd) {
            const between = plainText.slice(lastEnd, foundIndex)
            elements.push(
              <span key={`between-${index}`} className="text-slate-300">
                {between}
              </span>
            )
          }

          const wordIndex = index
          elements.push(
            <span
              key={`word-${index}`}
              ref={(el) => { wordRefs.current[index] = el }}
              onClick={() => onSeekToWord(wordIndex)}
              className="text-slate-300 transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50"
            >
              {plainText.slice(foundIndex, foundIndex + word.text.length)}
            </span>
          )

          lastEnd = foundIndex + word.text.length
          textPointer = lastEnd
          found = true
          break
        }
        searchStart = foundIndex + 1
      }

      // Strategy 2: If not found with boundaries, try lenient match
      if (!found && wordNormalized.length > 1) {
        const foundIndex = normalizeForMatch(plainText).indexOf(wordNormalized, textPointer)
        if (foundIndex !== -1 && foundIndex < textPointer + 200) {
          if (foundIndex > lastEnd) {
            const between = plainText.slice(lastEnd, foundIndex)
            elements.push(
              <span key={`between-${index}`} className="text-slate-300">
                {between}
              </span>
            )
          }

          const wordIndex = index
          elements.push(
            <span
              key={`word-${index}`}
              ref={(el) => { wordRefs.current[index] = el }}
              onClick={() => onSeekToWord(wordIndex)}
              className="text-slate-300 transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50"
            >
              {plainText.slice(foundIndex, foundIndex + word.text.length)}
            </span>
          )

          lastEnd = foundIndex + word.text.length
          textPointer = lastEnd
          found = true
        }
      }

      // Strategy 3: If still not found, try to find just the alphanumeric core of the word
      if (!found && wordNormalized.length > 2) {
        const alphanumericWord = wordNormalized.replace(/[^a-z0-9]/g, '')
        if (alphanumericWord.length > 2) {
          const searchText = normalizeForMatch(plainText)
          const foundIndex = searchText.indexOf(alphanumericWord, textPointer)
          if (foundIndex !== -1 && foundIndex < textPointer + 200) {
            let wordStart = foundIndex
            let wordEnd = foundIndex + alphanumericWord.length

            while (wordStart > 0 && !isWordBoundaryChar(plainText[wordStart - 1])) {
              wordStart--
            }
            while (wordEnd < plainText.length && !isWordBoundaryChar(plainText[wordEnd])) {
              wordEnd++
            }

            if (wordStart > lastEnd) {
              const between = plainText.slice(lastEnd, wordStart)
              elements.push(
                <span key={`between-${index}`} className="text-slate-300">
                  {between}
                </span>
              )
            }

            const wordIndex = index
            elements.push(
              <span
                key={`word-${index}`}
                ref={(el) => { wordRefs.current[index] = el }}
                onClick={() => onSeekToWord(wordIndex)}
                className="text-slate-300 transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50"
              >
                {plainText.slice(wordStart, wordEnd)}
              </span>
            )

            lastEnd = wordEnd
            textPointer = lastEnd
            found = true
          }
        }
      }

      // Strategy 4: If still not found, advance textPointer slightly to avoid getting stuck
      if (!found) {
        textPointer = Math.min(textPointer + 5, plainText.length)
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
  }, [words, plainText, onSeekToWord])

  return (
    <div className="prose prose-invert prose-slate max-w-none">
      {renderedContent}
    </div>
  )
}
