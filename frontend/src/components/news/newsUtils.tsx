import React from 'react'

// Lightweight markdown renderer for article content
// Supports: headings, lists, horizontal rules, bold, italic, links
// titleToSkip: optional title to skip (avoids duplicate title when metadata title is shown)
export function renderMarkdown(markdown: string, titleToSkip?: string | null): React.ReactNode[] {
  const lines = markdown.split('\n')
  const elements: React.ReactNode[] = []
  let key = 0
  let listItems: React.ReactNode[] = []
  let listType: 'ul' | 'ol' | null = null
  let skippedTitle = false  // Track if we've already skipped a matching title

  const flushList = () => {
    if (listItems.length > 0 && listType) {
      if (listType === 'ul') {
        elements.push(
          <ul key={key++} className="list-disc list-inside text-slate-300 mb-4 space-y-1 ml-4">
            {listItems}
          </ul>
        )
      } else {
        elements.push(
          <ol key={key++} className="list-decimal list-inside text-slate-300 mb-4 space-y-1 ml-4">
            {listItems}
          </ol>
        )
      }
      listItems = []
      listType = null
    }
  }

  // Process inline formatting (bold, italic, links)
  const processInline = (text: string): React.ReactNode => {
    // Replace **bold** and __bold__
    // Replace *italic* and _italic_
    // Replace [link](url)
    const parts: React.ReactNode[] = []
    let remaining = text
    let inlineKey = 0

    while (remaining.length > 0) {
      // Check for links first [text](url)
      const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/)
      if (linkMatch) {
        parts.push(
          <a
            key={inlineKey++}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 underline"
          >
            {linkMatch[1]}
          </a>
        )
        remaining = remaining.slice(linkMatch[0].length)
        continue
      }

      // Check for bold **text** or __text__
      const boldMatch = remaining.match(/^(\*\*|__)([^*_]+)\1/)
      if (boldMatch) {
        parts.push(<strong key={inlineKey++} className="font-semibold text-white">{boldMatch[2]}</strong>)
        remaining = remaining.slice(boldMatch[0].length)
        continue
      }

      // Check for italic *text* or _text_
      const italicMatch = remaining.match(/^(\*|_)([^*_]+)\1/)
      if (italicMatch) {
        parts.push(<em key={inlineKey++} className="italic">{italicMatch[2]}</em>)
        remaining = remaining.slice(italicMatch[0].length)
        continue
      }

      // Find next special character or end
      const nextSpecial = remaining.search(/[\[*_]/)
      if (nextSpecial === -1) {
        parts.push(remaining)
        break
      } else if (nextSpecial === 0) {
        // Not a match, take single character
        parts.push(remaining[0])
        remaining = remaining.slice(1)
      } else {
        parts.push(remaining.slice(0, nextSpecial))
        remaining = remaining.slice(nextSpecial)
      }
    }

    return parts.length === 1 ? parts[0] : parts
  }

  for (const line of lines) {
    const trimmed = line.trim()

    // Skip empty lines but flush any pending list
    if (trimmed === '') {
      flushList()
      continue
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(trimmed)) {
      flushList()
      elements.push(<hr key={key++} className="border-slate-600 my-6" />)
      continue
    }

    // Headings
    const h1Match = trimmed.match(/^#\s+(.+)$/)
    if (h1Match) {
      // Skip the first h1 if it's similar to the title (to avoid duplicate title display)
      // Uses fuzzy matching since extracted titles may differ slightly from metadata titles
      const headingText = h1Match[1].trim()
      if (titleToSkip && !skippedTitle) {
        const normalizedHeading = headingText.toLowerCase().replace(/[^\w\s]/g, '').trim()
        const normalizedTitle = titleToSkip.toLowerCase().replace(/[^\w\s]/g, '').trim()
        // Check if one contains the other, or they share significant overlap
        const isSimilar = normalizedHeading.includes(normalizedTitle) ||
                          normalizedTitle.includes(normalizedHeading) ||
                          normalizedHeading.startsWith(normalizedTitle.substring(0, 30)) ||
                          normalizedTitle.startsWith(normalizedHeading.substring(0, 30))
        if (isSimilar) {
          skippedTitle = true
          continue  // Skip this h1 since it's already shown in metadata
        }
      }
      flushList()
      elements.push(
        <h1 key={key++} className="text-2xl font-bold text-white mb-4 mt-6">
          {processInline(h1Match[1])}
        </h1>
      )
      continue
    }

    const h2Match = trimmed.match(/^##\s+(.+)$/)
    if (h2Match) {
      flushList()
      elements.push(
        <h2 key={key++} className="text-xl font-bold text-white mb-3 mt-5">
          {processInline(h2Match[1])}
        </h2>
      )
      continue
    }

    const h3Match = trimmed.match(/^###\s+(.+)$/)
    if (h3Match) {
      flushList()
      elements.push(
        <h3 key={key++} className="text-lg font-semibold text-white mb-2 mt-4">
          {processInline(h3Match[1])}
        </h3>
      )
      continue
    }

    const h4Match = trimmed.match(/^####\s+(.+)$/)
    if (h4Match) {
      flushList()
      elements.push(
        <h4 key={key++} className="text-base font-semibold text-white mb-2 mt-3">
          {processInline(h4Match[1])}
        </h4>
      )
      continue
    }

    // Unordered list items (- or *)
    const ulMatch = trimmed.match(/^[-*]\s+(.+)$/)
    if (ulMatch) {
      if (listType !== 'ul') {
        flushList()
        listType = 'ul'
      }
      listItems.push(<li key={key++}>{processInline(ulMatch[1])}</li>)
      continue
    }

    // Ordered list items (1. 2. etc)
    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/)
    if (olMatch) {
      if (listType !== 'ol') {
        flushList()
        listType = 'ol'
      }
      listItems.push(<li key={key++}>{processInline(olMatch[1])}</li>)
      continue
    }

    // Regular paragraph
    flushList()
    elements.push(
      <p key={key++} className="text-slate-300 leading-relaxed mb-4">
        {processInline(trimmed)}
      </p>
    )
  }

  // Flush any remaining list
  flushList()

  return elements
}

// Format relative time (e.g., "2 hours ago")
export function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return ''

  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}

import { NEWS_CATEGORIES } from '../../types/newsTypes'

// Build a category-order index for fast sorting (lower index = earlier in list)
const _categoryOrder: Record<string, number> = Object.fromEntries(
  NEWS_CATEGORIES.map((cat, i) => [cat, i])
)

/** Sort sources by their category order (matching NEWS_CATEGORIES), then alphabetically within a category */
export function sortSourcesByCategory<T extends { id: string; category?: string }>(
  sources: T[],
): T[] {
  return [...sources].sort((a, b) => {
    const orderA = _categoryOrder[a.category || ''] ?? 999
    const orderB = _categoryOrder[b.category || ''] ?? 999
    if (orderA !== orderB) return orderA - orderB
    return a.id.localeCompare(b.id)
  })
}
