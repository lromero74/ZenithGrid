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

// Source-to-category mapping (used to color sources by their category)
import { CATEGORY_COLORS, NEWS_CATEGORIES } from '../../pages/news/types'

export const SOURCE_CATEGORY: Record<string, string> = {
  // CryptoCurrency
  bitcoin_magazine: 'CryptoCurrency', blockworks: 'CryptoCurrency',
  coindesk: 'CryptoCurrency', cointelegraph: 'CryptoCurrency',
  decrypt: 'CryptoCurrency', cryptoslate: 'CryptoCurrency',
  beincrypto: 'CryptoCurrency', unchained: 'CryptoCurrency',
  newsbtc: 'CryptoCurrency', cryptopotato: 'CryptoCurrency',
  bitcoinist: 'CryptoCurrency', u_today: 'CryptoCurrency',
  coinjournal: 'CryptoCurrency', the_crypto_basic: 'CryptoCurrency',
  crypto_briefing: 'CryptoCurrency', watcher_guru: 'CryptoCurrency',
  blockchain_news: 'CryptoCurrency',
  // AI
  openai_blog: 'AI', mit_tech_ai: 'AI', the_ai_beat: 'AI',
  // Finance
  yahoo_finance_news: 'Finance', motley_fool: 'Finance', kiplinger: 'Finance',
  // World
  voa_news: 'World', global_voices: 'World', rferl: 'World',
  africanews: 'World', scmp: 'World', cnn_world: 'World',
  // Politics
  cnn_politics: 'Politics',
  // Nation
  npr_news: 'Nation', pbs_newshour: 'Nation', ap_news: 'Nation',
  cnn_us: 'Nation',
  // Business
  cnbc_business: 'Business', business_insider: 'Business',
  cnn_business: 'Business',
  // Technology
  engadget: 'Technology', ars_technica: 'Technology',
  the_verge: 'Technology', wired: 'Technology', cnn_tech: 'Technology',
  // Entertainment
  variety: 'Entertainment', hollywood_reporter: 'Entertainment',
  deadline: 'Entertainment', cnn_entertainment: 'Entertainment',
  // Sports
  espn: 'Sports', cbs_sports: 'Sports', yahoo_sports: 'Sports',
  // Science
  science_daily: 'Science', nasa: 'Science',
  quanta_magazine: 'Science', sciencealert: 'Science',
  futurism: 'Science', live_science: 'Science',
  space_com: 'Science', smithsonian: 'Science',
  // Health
  stat_news: 'Health', npr_health: 'Health', science_daily_health: 'Health',
  genetic_engineering_news: 'Health', cnn_health: 'Health',
  nature_medicine: 'Health', the_lancet: 'Health', who_news: 'Health',
  nutrition_org: 'Health', self_wellness: 'Health',
}

export const VIDEO_SOURCE_CATEGORY: Record<string, string> = {
  // CryptoCurrency
  coin_bureau: 'CryptoCurrency', benjamin_cowen: 'CryptoCurrency',
  altcoin_daily: 'CryptoCurrency', bankless: 'CryptoCurrency',
  the_defiant: 'CryptoCurrency', crypto_banter: 'CryptoCurrency',
  datadash: 'CryptoCurrency', cryptosrus: 'CryptoCurrency',
  the_moon: 'CryptoCurrency', digital_asset_news: 'CryptoCurrency',
  paul_barron: 'CryptoCurrency', lark_davis: 'CryptoCurrency',
  pompliano: 'CryptoCurrency', whiteboard_crypto: 'CryptoCurrency',
  // AI
  two_minute_papers: 'AI', ai_explained: 'AI', matt_wolfe: 'AI',
  // Finance
  financial_times: 'Finance', graham_stephan: 'Finance',
  // Business
  cnbc_yt: 'Business', bloomberg: 'Business', yahoo_finance: 'Business',
  // World
  wion: 'World', dw_news: 'World', channel4_news: 'World',
  // Nation
  pbs_newshour_yt: 'Nation', nbc_news: 'Nation', abc_news: 'Nation',
  // Technology
  mkbhd: 'Technology', linus_tech_tips: 'Technology', the_verge_yt: 'Technology',
  // Entertainment
  screen_junkies: 'Entertainment', collider: 'Entertainment', ign: 'Entertainment',
  // Sports
  espn_yt: 'Sports', cbs_sports_yt: 'Sports', pat_mcafee: 'Sports',
  // Science
  veritasium: 'Science', kurzgesagt: 'Science', smarter_every_day: 'Science',
  // Health
  doctor_mike: 'Health', medlife_crisis: 'Health', dr_eric_berg: 'Health',
}

// Build source color maps from category colors
function buildColorMap(mapping: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [source, category] of Object.entries(mapping)) {
    result[source] = CATEGORY_COLORS[category] || 'bg-slate-600 text-slate-300 border-slate-500'
  }
  return result
}

export const sourceColors: Record<string, string> = buildColorMap(SOURCE_CATEGORY)
export const videoSourceColors: Record<string, string> = buildColorMap(VIDEO_SOURCE_CATEGORY)

// Build a category-order index for fast sorting (lower index = earlier in list)
const _categoryOrder: Record<string, number> = Object.fromEntries(
  NEWS_CATEGORIES.map((cat, i) => [cat, i])
)

/** Sort sources by their category order (matching NEWS_CATEGORIES), then alphabetically within a category */
export function sortSourcesByCategory<T extends { id: string }>(
  sources: T[],
  categoryMap: Record<string, string>,
): T[] {
  return [...sources].sort((a, b) => {
    const catA = categoryMap[a.id] || 'zzz'
    const catB = categoryMap[b.id] || 'zzz'
    const orderA = _categoryOrder[catA] ?? 999
    const orderB = _categoryOrder[catB] ?? 999
    if (orderA !== orderB) return orderA - orderB
    return a.id.localeCompare(b.id)
  })
}
