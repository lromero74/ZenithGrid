/**
 * Crypto News Page
 *
 * Displays aggregated crypto news from multiple sources with 24-hour caching.
 * Sources include Reddit, CoinDesk, CoinTelegraph, Decrypt, The Block, and CryptoSlate.
 * Also includes video news from reputable crypto YouTube channels.
 */

import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Newspaper, ExternalLink, RefreshCw, Clock, Filter, Video, Play, Gauge, Timer, DollarSign, ToggleLeft, ToggleRight, X, BookOpen, AlertCircle } from 'lucide-react'
import { LoadingSpinner } from '../components/LoadingSpinner'

// BTC Halving constants
const NEXT_HALVING_BLOCK = 1050000 // Block 1,050,000 is the next halving
const BLOCKS_PER_HALVING = 210000
const AVG_BLOCK_TIME_MINUTES = 10 // Average Bitcoin block time

interface FearGreedData {
  value: number
  value_classification: string
  timestamp: string
  time_until_update: string | null
}

interface FearGreedResponse {
  data: FearGreedData
  cached_at: string
  cache_expires_at: string
}

interface NewsItem {
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  summary: string | null
  thumbnail: string | null
}

interface VideoItem {
  title: string
  url: string
  video_id: string
  source: string
  source_name: string
  channel_name: string
  published: string | null
  thumbnail: string | null
  description: string | null
}

interface NewsSource {
  id: string
  name: string
  website: string
}

interface VideoSource {
  id: string
  name: string
  website: string
  description: string
}

interface NewsResponse {
  news: NewsItem[]
  sources: NewsSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

interface VideoResponse {
  videos: VideoItem[]
  sources: VideoSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

interface BlockHeightResponse {
  height: number
  timestamp: string
}

interface USDebtResponse {
  total_debt: number
  debt_per_second: number
  gdp: number
  debt_to_gdp_ratio: number
  record_date: string
  cached_at: string
  cache_expires_at: string
}

interface ArticleContentResponse {
  url: string
  title: string | null
  content: string | null
  author: string | null
  date: string | null
  success: boolean
  error: string | null
}

interface HalvingCountdown {
  blocksRemaining: number
  estimatedDate: Date
  daysRemaining: number
  hoursRemaining: number
  minutesRemaining: number
  percentComplete: number
}

// Lightweight markdown renderer for article content
// Supports: headings, lists, horizontal rules, bold, italic, links
// titleToSkip: optional title to skip (avoids duplicate title when metadata title is shown)
function renderMarkdown(markdown: string, titleToSkip?: string | null): React.ReactNode[] {
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
function formatRelativeTime(isoString: string | null): string {
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

// Source colors for visual distinction
const sourceColors: Record<string, string> = {
  reddit_crypto: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  reddit_bitcoin: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  coindesk: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  cointelegraph: 'bg-green-500/20 text-green-400 border-green-500/30',
  decrypt: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  theblock: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  cryptoslate: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
}

// Video channel colors
const videoSourceColors: Record<string, string> = {
  coin_bureau: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  benjamin_cowen: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  altcoin_daily: 'bg-red-500/20 text-red-400 border-red-500/30',
  bankless: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  the_defiant: 'bg-green-500/20 text-green-400 border-green-500/30',
  crypto_banter: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
}

// Get color for Fear/Greed meter based on value
function getFearGreedColor(value: number): { bg: string; text: string; border: string; gradient: string } {
  if (value <= 25) {
    return {
      bg: 'bg-red-500/20',
      text: 'text-red-400',
      border: 'border-red-500/30',
      gradient: 'from-red-600 to-red-400',
    }
  } else if (value <= 45) {
    return {
      bg: 'bg-orange-500/20',
      text: 'text-orange-400',
      border: 'border-orange-500/30',
      gradient: 'from-orange-600 to-orange-400',
    }
  } else if (value <= 55) {
    return {
      bg: 'bg-yellow-500/20',
      text: 'text-yellow-400',
      border: 'border-yellow-500/30',
      gradient: 'from-yellow-600 to-yellow-400',
    }
  } else if (value <= 75) {
    return {
      bg: 'bg-lime-500/20',
      text: 'text-lime-400',
      border: 'border-lime-500/30',
      gradient: 'from-lime-600 to-lime-400',
    }
  } else {
    return {
      bg: 'bg-green-500/20',
      text: 'text-green-400',
      border: 'border-green-500/30',
      gradient: 'from-green-600 to-green-400',
    }
  }
}

// Format large numbers with commas and optional prefix
function formatDebt(value: number): string {
  // Format to 2 decimal places and add commas
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

// Format the countdown in extended format (years, months, days, hours, minutes, seconds)
function formatExtendedCountdown(diffMs: number): string {
  if (diffMs <= 0) return 'Halving imminent!'

  // Calculate total days first
  const totalDays = diffMs / (1000 * 60 * 60 * 24)

  // Approximate years and months (using average days)
  const years = Math.floor(totalDays / 365.25)
  const remainingAfterYears = totalDays - (years * 365.25)
  const months = Math.floor(remainingAfterYears / 30.44)
  const remainingAfterMonths = remainingAfterYears - (months * 30.44)
  const days = Math.floor(remainingAfterMonths)

  // Calculate time components from remaining milliseconds
  const remainingMs = diffMs - (Math.floor(totalDays) * 24 * 60 * 60 * 1000)
  const hours = Math.floor(remainingMs / (1000 * 60 * 60))
  const mins = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60))
  const secs = Math.floor((remainingMs % (1000 * 60)) / 1000)

  const parts: string[] = []
  if (years > 0) parts.push(`${years}y`)
  if (months > 0) parts.push(`${months}mo`)
  if (days > 0) parts.push(`${days}d`)
  parts.push(`${hours}h ${mins}m ${secs}s`)

  return parts.join(' ')
}

// Calculate halving countdown from current block height
function calculateHalvingCountdown(currentHeight: number): HalvingCountdown {
  const blocksRemaining = NEXT_HALVING_BLOCK - currentHeight
  const minutesRemaining = blocksRemaining * AVG_BLOCK_TIME_MINUTES
  const estimatedDate = new Date(Date.now() + minutesRemaining * 60 * 1000)

  const totalMinutes = minutesRemaining
  const days = Math.floor(totalMinutes / (24 * 60))
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60)
  const minutes = Math.floor(totalMinutes % 60)

  // Progress through current halving epoch (210,000 blocks)
  const currentEpochStart = NEXT_HALVING_BLOCK - BLOCKS_PER_HALVING
  const blocksIntoEpoch = currentHeight - currentEpochStart
  const percentComplete = (blocksIntoEpoch / BLOCKS_PER_HALVING) * 100

  return {
    blocksRemaining,
    estimatedDate,
    daysRemaining: days,
    hoursRemaining: hours,
    minutesRemaining: minutes,
    percentComplete: Math.min(100, Math.max(0, percentComplete)),
  }
}

type TabType = 'articles' | 'videos'

export default function News() {
  const [selectedSource, setSelectedSource] = useState<string>('all')
  const [selectedVideoSource, setSelectedVideoSource] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<TabType>('articles')
  // Track which video is playing inline (null means none)
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null)
  // Track which article is being previewed (null means none)
  const [previewArticle, setPreviewArticle] = useState<NewsItem | null>(null)
  // Track article reader mode content
  const [articleContent, setArticleContent] = useState<ArticleContentResponse | null>(null)
  const [articleContentLoading, setArticleContentLoading] = useState(false)
  const [readerModeEnabled, setReaderModeEnabled] = useState(false)

  // Fetch article content when reader mode is enabled
  useEffect(() => {
    if (!previewArticle || !readerModeEnabled) {
      return
    }

    const fetchArticleContent = async () => {
      setArticleContentLoading(true)
      setArticleContent(null)

      try {
        const response = await fetch(`/api/news/article-content?url=${encodeURIComponent(previewArticle.url)}`)
        if (!response.ok) {
          throw new Error('Failed to fetch article content')
        }
        const data: ArticleContentResponse = await response.json()
        setArticleContent(data)
      } catch {
        setArticleContent({
          url: previewArticle.url,
          title: null,
          content: null,
          author: null,
          date: null,
          success: false,
          error: 'Failed to connect to article extraction service'
        })
      } finally {
        setArticleContentLoading(false)
      }
    }

    fetchArticleContent()
  }, [previewArticle, readerModeEnabled])

  // Reset reader mode when closing modal
  const handleCloseModal = () => {
    setPreviewArticle(null)
    setReaderModeEnabled(false)
    setArticleContent(null)
  }

  // Force re-render every minute to update relative timestamps
  const [, setTimeTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeTick((t) => t + 1)
    }, 60000) // Update every minute
    return () => clearInterval(interval)
  }, [])

  // Fetch news articles
  const {
    data: newsData,
    isLoading: newsLoading,
    error: newsError,
    refetch: refetchNews,
    isFetching: newsFetching,
  } = useQuery<NewsResponse>({
    queryKey: ['crypto-news'],
    queryFn: async () => {
      const response = await fetch('/api/news/')
      if (!response.ok) throw new Error('Failed to fetch news')
      return response.json()
    },
    staleTime: 1000 * 60 * 60, // Consider fresh for 1 hour
    refetchOnWindowFocus: false,
  })

  // Fetch video news
  const {
    data: videoData,
    isLoading: videosLoading,
    error: videosError,
    refetch: refetchVideos,
    isFetching: videosFetching,
  } = useQuery<VideoResponse>({
    queryKey: ['crypto-videos'],
    queryFn: async () => {
      const response = await fetch('/api/news/videos')
      if (!response.ok) throw new Error('Failed to fetch videos')
      return response.json()
    },
    staleTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
  })

  // Fetch Fear & Greed Index (15 minute refresh)
  const { data: fearGreedData } = useQuery<FearGreedResponse>({
    queryKey: ['fear-greed'],
    queryFn: async () => {
      const response = await fetch('/api/news/fear-greed')
      if (!response.ok) throw new Error('Failed to fetch fear/greed index')
      return response.json()
    },
    staleTime: 1000 * 60 * 15, // 15 minutes
    refetchInterval: 1000 * 60 * 15, // Refetch every 15 minutes
    refetchOnWindowFocus: false,
  })

  // Fetch BTC block height for halving countdown
  const { data: blockHeight } = useQuery<BlockHeightResponse>({
    queryKey: ['btc-block-height'],
    queryFn: async () => {
      const response = await fetch('/api/news/btc-block-height')
      if (!response.ok) throw new Error('Failed to fetch block height')
      return response.json()
    },
    staleTime: 1000 * 60 * 10, // 10 minutes
    refetchInterval: 1000 * 60 * 10, // Refetch every 10 minutes
    refetchOnWindowFocus: false,
  })

  // Fetch US National Debt
  const { data: usDebtData } = useQuery<USDebtResponse>({
    queryKey: ['us-debt'],
    queryFn: async () => {
      const response = await fetch('/api/news/us-debt')
      if (!response.ok) throw new Error('Failed to fetch US debt')
      return response.json()
    },
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
    refetchInterval: 1000 * 60 * 60 * 24, // Refetch once per day
    refetchOnWindowFocus: false,
  })

  // Calculate halving countdown
  const halvingCountdown = blockHeight ? calculateHalvingCountdown(blockHeight.height) : null

  // Toggle for extended countdown format (years/months)
  const [showExtendedCountdown, setShowExtendedCountdown] = useState(false)

  // Live countdown timer - use blockHeight.height as stable dependency
  const [liveCountdown, setLiveCountdown] = useState<string>('')
  const targetTimeRef = useRef<number>(0)

  // Calculate target time once when block height changes
  useEffect(() => {
    if (!blockHeight?.height) return
    const blocksRemaining = NEXT_HALVING_BLOCK - blockHeight.height
    const minutesRemaining = blocksRemaining * AVG_BLOCK_TIME_MINUTES
    targetTimeRef.current = Date.now() + minutesRemaining * 60 * 1000
  }, [blockHeight?.height])

  // Update countdown display every second
  useEffect(() => {
    if (!blockHeight?.height) return

    const updateCountdown = () => {
      const now = Date.now()
      const diff = targetTimeRef.current - now
      if (diff <= 0) {
        setLiveCountdown('Halving imminent!')
        return
      }

      if (showExtendedCountdown) {
        setLiveCountdown(formatExtendedCountdown(diff))
      } else {
        const days = Math.floor(diff / (1000 * 60 * 60 * 24))
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
        const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
        const secs = Math.floor((diff % (1000 * 60)) / 1000)
        setLiveCountdown(`${days}d ${hours}h ${mins}m ${secs}s`)
      }
    }

    updateCountdown()
    const interval = setInterval(updateCountdown, 1000)
    return () => clearInterval(interval)
  }, [blockHeight?.height, showExtendedCountdown])

  // Animated US debt counter
  const [liveDebt, setLiveDebt] = useState<number>(0)
  const debtStartTimeRef = useRef<number>(0)
  const debtBaseValueRef = useRef<number>(0)

  useEffect(() => {
    if (!usDebtData) return

    // Store the base debt value and start time
    debtBaseValueRef.current = usDebtData.total_debt
    debtStartTimeRef.current = Date.now()
    setLiveDebt(usDebtData.total_debt)

    // Update debt counter 10 times per second for smooth animation
    const updateDebt = () => {
      const elapsedSeconds = (Date.now() - debtStartTimeRef.current) / 1000
      const newDebt = debtBaseValueRef.current + (elapsedSeconds * usDebtData.debt_per_second)
      setLiveDebt(newDebt)
    }

    const interval = setInterval(updateDebt, 100) // Update every 100ms
    return () => clearInterval(interval)
  }, [usDebtData])

  const handleForceRefresh = async () => {
    if (activeTab === 'articles') {
      await fetch('/api/news/?force_refresh=true')
      refetchNews()
    } else {
      await fetch('/api/news/videos?force_refresh=true')
      refetchVideos()
    }
  }

  // Filter news by selected source
  const filteredNews =
    selectedSource === 'all'
      ? newsData?.news || []
      : newsData?.news.filter((item) => item.source === selectedSource) || []

  // Filter videos by selected source
  const filteredVideos =
    selectedVideoSource === 'all'
      ? videoData?.videos || []
      : videoData?.videos.filter((item) => item.source === selectedVideoSource) || []

  // Get unique sources from actual news items
  const availableSources = newsData?.sources || []
  const availableVideoSources = videoData?.sources || []

  const isLoading = activeTab === 'articles' ? newsLoading : videosLoading
  const error = activeTab === 'articles' ? newsError : videosError
  const isFetching = activeTab === 'articles' ? newsFetching : videosFetching
  const cacheData = activeTab === 'articles' ? newsData : videoData

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <LoadingSpinner size="lg" text={activeTab === 'articles' ? 'Loading crypto news...' : 'Loading crypto videos...'} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-center">
        <p className="text-red-400">Failed to load {activeTab}. Please try again later.</p>
        <button
          onClick={() => activeTab === 'articles' ? refetchNews() : refetchVideos()}
          className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-red-400 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center space-x-3">
          <Newspaper className="w-8 h-8 text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold">Crypto News</h1>
            <p className="text-sm text-slate-400">
              Aggregated from {availableSources.length + availableVideoSources.length} trusted sources
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          {/* Cache info */}
          {cacheData && (
            <div className="flex items-center space-x-2 text-xs text-slate-500">
              <Clock className="w-3 h-3" />
              <span>
                Cached {formatRelativeTime(cacheData.cached_at)}
              </span>
            </div>
          )}

          {/* Refresh button */}
          <button
            onClick={handleForceRefresh}
            disabled={isFetching}
            className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            <span className="text-sm">Refresh</span>
          </button>
        </div>
      </div>

      {/* Market Sentiment & Halving Dashboard */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Fear & Greed Index */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <Gauge className="w-5 h-5 text-slate-400" />
            <h3 className="font-medium text-white">Fear & Greed Index</h3>
          </div>

          {fearGreedData ? (
            <div className="flex flex-col items-center">
              {/* Semicircular gauge */}
              <div className="relative w-48 h-24 mb-2">
                {/* Background arc */}
                <svg viewBox="0 0 200 100" className="w-full h-full">
                  {/* Gradient background arc */}
                  <defs>
                    <linearGradient id="fearGreedGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#ef4444" />
                      <stop offset="25%" stopColor="#f97316" />
                      <stop offset="50%" stopColor="#eab308" />
                      <stop offset="75%" stopColor="#84cc16" />
                      <stop offset="100%" stopColor="#22c55e" />
                    </linearGradient>
                  </defs>
                  {/* Background track */}
                  <path
                    d="M 20 95 A 80 80 0 0 1 180 95"
                    fill="none"
                    stroke="#334155"
                    strokeWidth="12"
                    strokeLinecap="round"
                  />
                  {/* Colored arc */}
                  <path
                    d="M 20 95 A 80 80 0 0 1 180 95"
                    fill="none"
                    stroke="url(#fearGreedGradient)"
                    strokeWidth="12"
                    strokeLinecap="round"
                  />
                  {/* Needle */}
                  <g transform={`rotate(${-90 + (fearGreedData.data.value / 100) * 180}, 100, 95)`}>
                    <line
                      x1="100"
                      y1="95"
                      x2="100"
                      y2="30"
                      stroke="white"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                    <circle cx="100" cy="95" r="6" fill="white" />
                  </g>
                </svg>
              </div>

              {/* Value display */}
              <div className={`text-4xl font-bold ${getFearGreedColor(fearGreedData.data.value).text}`}>
                {fearGreedData.data.value}
              </div>
              <div
                className={`px-3 py-1 rounded-full text-sm font-medium mt-1 ${getFearGreedColor(fearGreedData.data.value).bg} ${getFearGreedColor(fearGreedData.data.value).text} border ${getFearGreedColor(fearGreedData.data.value).border}`}
              >
                {fearGreedData.data.value_classification}
              </div>

              {/* Scale labels */}
              <div className="flex justify-between w-full mt-3 text-xs text-slate-500">
                <span>Extreme Fear</span>
                <span>Neutral</span>
                <span>Extreme Greed</span>
              </div>

              {/* Cache info */}
              <div className="mt-3 text-xs text-slate-600">
                Updates every 15 minutes
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        {/* BTC Halving Countdown */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Timer className="w-5 h-5 text-orange-400" />
              <h3 className="font-medium text-white">Next BTC Halving</h3>
            </div>
            {/* Format toggle */}
            <button
              onClick={() => setShowExtendedCountdown(!showExtendedCountdown)}
              className="flex items-center space-x-1 px-2 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded transition-colors"
              title={showExtendedCountdown ? 'Show short format (days)' : 'Show extended format (years/months)'}
            >
              {showExtendedCountdown ? (
                <ToggleRight className="w-4 h-4 text-orange-400" />
              ) : (
                <ToggleLeft className="w-4 h-4 text-slate-400" />
              )}
              <span className="text-slate-400">{showExtendedCountdown ? 'Y/M/D' : 'Days'}</span>
            </button>
          </div>

          {halvingCountdown && blockHeight ? (
            <div className="flex flex-col items-center">
              {/* Live countdown */}
              <div className="text-3xl font-mono font-bold text-orange-400 mb-2">
                {liveCountdown || 'Calculating...'}
              </div>

              {/* Estimated date */}
              <div className="text-sm text-slate-400 mb-4">
                ~{halvingCountdown.estimatedDate.toLocaleDateString('en-US', {
                  month: 'long',
                  year: 'numeric',
                })}
              </div>

              {/* Progress bar */}
              <div className="w-full mb-2">
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Epoch Progress</span>
                  <span>{halvingCountdown.percentComplete.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-orange-600 to-yellow-500 transition-all duration-500"
                    style={{ width: `${halvingCountdown.percentComplete}%` }}
                  />
                </div>
              </div>

              {/* Block info */}
              <div className="grid grid-cols-2 gap-4 w-full mt-3 text-center">
                <div className="bg-slate-900/50 rounded-lg p-2">
                  <div className="text-xs text-slate-500">Current Block</div>
                  <div className="text-sm font-mono text-slate-300">
                    {blockHeight.height.toLocaleString()}
                  </div>
                </div>
                <div className="bg-slate-900/50 rounded-lg p-2">
                  <div className="text-xs text-slate-500">Blocks Remaining</div>
                  <div className="text-sm font-mono text-orange-400">
                    {halvingCountdown.blocksRemaining.toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Halving info */}
              <div className="mt-3 text-xs text-slate-600 text-center">
                Block reward will drop from 3.125 to 1.5625 BTC
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        {/* US National Debt */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <DollarSign className="w-5 h-5 text-green-400" />
            <h3 className="font-medium text-white">US National Debt</h3>
          </div>

          {usDebtData ? (
            <div className="flex flex-col items-center">
              {/* Animated debt counter */}
              <div className="text-2xl font-mono font-bold text-red-400 mb-2 tracking-tight">
                ${formatDebt(liveDebt)}
              </div>

              {/* Debt rate */}
              <div className="text-xs text-slate-400 mb-3">
                {usDebtData.debt_per_second > 0 ? '+' : ''}
                ${formatDebt(usDebtData.debt_per_second)}/sec
              </div>

              {/* Debt-to-GDP ratio */}
              <div className="w-full bg-slate-900/50 rounded-lg p-3 mb-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs text-slate-500">Debt-to-GDP Ratio</span>
                  <span className={`text-sm font-bold ${usDebtData.debt_to_gdp_ratio > 100 ? 'text-red-400' : 'text-yellow-400'}`}>
                    {usDebtData.debt_to_gdp_ratio.toFixed(1)}%
                  </span>
                </div>
                {/* Progress bar */}
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      usDebtData.debt_to_gdp_ratio > 100
                        ? 'bg-gradient-to-r from-red-600 to-red-400'
                        : 'bg-gradient-to-r from-yellow-600 to-yellow-400'
                    }`}
                    style={{ width: `${Math.min(150, usDebtData.debt_to_gdp_ratio)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-600 mt-1">
                  <span>0%</span>
                  <span>100%</span>
                  <span>150%</span>
                </div>
              </div>

              {/* GDP value */}
              <div className="text-xs text-slate-500">
                GDP: ${(usDebtData.gdp / 1_000_000_000_000).toFixed(2)}T
              </div>

              {/* Data source */}
              <div className="mt-2 text-[10px] text-slate-600">
                Source: Treasury Fiscal Data • FRED
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex space-x-1 bg-slate-800 rounded-lg p-1 w-fit">
        <button
          onClick={() => setActiveTab('articles')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'articles'
              ? 'bg-blue-500/20 text-blue-400'
              : 'text-slate-400 hover:text-white hover:bg-slate-700'
          }`}
        >
          <Newspaper className="w-4 h-4" />
          <span>Articles</span>
          <span className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">
            {newsData?.total_items || 0}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('videos')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'videos'
              ? 'bg-red-500/20 text-red-400'
              : 'text-slate-400 hover:text-white hover:bg-slate-700'
          }`}
        >
          <Video className="w-4 h-4" />
          <span>Videos</span>
          <span className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">
            {videoData?.total_items || 0}
          </span>
        </button>
      </div>

      {/* Articles Tab */}
      {activeTab === 'articles' && (
        <>
          {/* Source filter */}
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <button
              onClick={() => setSelectedSource('all')}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedSource === 'all'
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              All ({newsData?.total_items || 0})
            </button>
            {availableSources.map((source) => {
              const count = newsData?.news.filter((n) => n.source === source.id).length || 0
              return (
                <button
                  key={source.id}
                  onClick={() => setSelectedSource(source.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    selectedSource === source.id
                      ? sourceColors[source.id] || 'bg-slate-600 text-white'
                      : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {source.name.replace('Reddit ', 'r/')} ({count})
                </button>
              )
            })}
          </div>

          {/* News grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredNews.map((item, index) => (
              <div
                key={`${item.source}-${index}`}
                className="group bg-slate-800 border border-slate-700 rounded-lg overflow-hidden hover:border-slate-600 transition-all hover:shadow-lg hover:shadow-slate-900/50"
              >
                {/* Thumbnail with preview/external link buttons */}
                <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
                  {item.thumbnail && (
                    <img
                      src={item.thumbnail}
                      alt=""
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  )}
                  {/* Click overlay to open preview */}
                  <button
                    onClick={() => setPreviewArticle(item)}
                    className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/30 transition-colors cursor-pointer"
                  />
                  {/* Open in new tab button */}
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                    title="Open on website"
                  >
                    <ExternalLink className="w-4 h-4 text-white" />
                  </a>
                </div>

                <button
                  onClick={() => setPreviewArticle(item)}
                  className="p-4 space-y-3 text-left w-full cursor-pointer hover:bg-slate-700/30 transition-colors"
                >
                  {/* Source badge and time */}
                  <div className="flex items-center justify-between">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium border ${
                        sourceColors[item.source] || 'bg-slate-600 text-slate-300'
                      }`}
                    >
                      {item.source_name}
                    </span>
                    {item.published && (
                      <span className="text-xs text-slate-500">
                        {formatRelativeTime(item.published)}
                      </span>
                    )}
                  </div>

                  {/* Title */}
                  <h3 className="font-medium text-white group-hover:text-blue-400 transition-colors line-clamp-3">
                    {item.title}
                  </h3>

                  {/* Summary */}
                  {item.summary && (
                    <p className="text-sm text-slate-400 line-clamp-2">{item.summary}</p>
                  )}

                  {/* Click to preview indicator */}
                  <div className="flex items-center space-x-1 text-xs text-slate-500 group-hover:text-blue-400 transition-colors">
                    <Newspaper className="w-3 h-3" />
                    <span>Click to preview</span>
                  </div>
                </button>
              </div>
            ))}
          </div>

          {/* Empty state */}
          {filteredNews.length === 0 && (
            <div className="text-center py-12">
              <Newspaper className="w-12 h-12 text-slate-600 mx-auto mb-4" />
              <p className="text-slate-400">No news articles found</p>
              {selectedSource !== 'all' && (
                <button
                  onClick={() => setSelectedSource('all')}
                  className="mt-2 text-blue-400 hover:text-blue-300"
                >
                  Show all sources
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Videos Tab */}
      {activeTab === 'videos' && (
        <>
          {/* Video source filter */}
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <button
              onClick={() => setSelectedVideoSource('all')}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedVideoSource === 'all'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              All ({videoData?.total_items || 0})
            </button>
            {availableVideoSources.map((source) => {
              const count = videoData?.videos.filter((v) => v.source === source.id).length || 0
              return (
                <button
                  key={source.id}
                  onClick={() => setSelectedVideoSource(source.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    selectedVideoSource === source.id
                      ? videoSourceColors[source.id] || 'bg-slate-600 text-white'
                      : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {source.name} ({count})
                </button>
              )
            })}
          </div>

          {/* Videos grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredVideos.map((video, index) => {
              const isPlaying = playingVideoId === video.video_id

              return (
                <div
                  key={`${video.source}-${index}`}
                  className="group bg-slate-800 border border-slate-700 rounded-lg overflow-hidden hover:border-slate-600 transition-all hover:shadow-lg hover:shadow-slate-900/50"
                >
                  {/* Video area - either thumbnail or embedded player */}
                  <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
                    {isPlaying ? (
                      // Embedded YouTube player
                      <>
                        <iframe
                          src={`https://www.youtube.com/embed/${video.video_id}?autoplay=1&rel=0`}
                          title={video.title}
                          className="w-full h-full"
                          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                          allowFullScreen
                        />
                        {/* Close button */}
                        <button
                          onClick={() => setPlayingVideoId(null)}
                          className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                          title="Close video"
                        >
                          <X className="w-5 h-5 text-white" />
                        </button>
                      </>
                    ) : (
                      // Thumbnail with play button
                      <>
                        {video.thumbnail && (
                          <img
                            src={video.thumbnail}
                            alt=""
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none'
                            }}
                          />
                        )}
                        {/* Play button overlay - click to play inline */}
                        <button
                          onClick={() => setPlayingVideoId(video.video_id)}
                          className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/40 transition-colors cursor-pointer"
                        >
                          <div className="w-14 h-14 bg-red-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
                            <Play className="w-7 h-7 text-white ml-1" fill="white" />
                          </div>
                        </button>
                        {/* Open in new tab button */}
                        <a
                          href={video.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                          title="Open on YouTube"
                        >
                          <ExternalLink className="w-4 h-4 text-white" />
                        </a>
                      </>
                    )}
                  </div>

                  <div className="p-4 space-y-3">
                    {/* Channel badge and time */}
                    <div className="flex items-center justify-between">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium border ${
                          videoSourceColors[video.source] || 'bg-slate-600 text-slate-300'
                        }`}
                      >
                        {video.channel_name}
                      </span>
                      {video.published && (
                        <span className="text-xs text-slate-500">
                          {formatRelativeTime(video.published)}
                        </span>
                      )}
                    </div>

                    {/* Title */}
                    <h3 className="font-medium text-white line-clamp-2">
                      {video.title}
                    </h3>

                    {/* Description */}
                    {video.description && (
                      <p className="text-sm text-slate-400 line-clamp-2">{video.description}</p>
                    )}

                    {/* Action link */}
                    <a
                      href={video.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center space-x-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span>Open on YouTube</span>
                    </a>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Empty state for videos */}
          {filteredVideos.length === 0 && (
            <div className="text-center py-12">
              <Video className="w-12 h-12 text-slate-600 mx-auto mb-4" />
              <p className="text-slate-400">No videos found</p>
              {selectedVideoSource !== 'all' && (
                <button
                  onClick={() => setSelectedVideoSource('all')}
                  className="mt-2 text-red-400 hover:text-red-300"
                >
                  Show all channels
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Sources footer */}
      <div className="border-t border-slate-700 pt-6">
        <h3 className="text-sm font-medium text-slate-400 mb-3">
          {activeTab === 'articles' ? 'News Sources' : 'Video Channels'}
        </h3>
        <div className="flex flex-wrap gap-3">
          {activeTab === 'articles' ? (
            availableSources.map((source) => (
              <a
                key={source.id}
                href={source.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 hover:text-blue-400 transition-colors"
              >
                {source.name} ↗
              </a>
            ))
          ) : (
            availableVideoSources.map((source) => (
              <a
                key={source.id}
                href={source.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                title={source.description}
              >
                {source.name} ↗
              </a>
            ))
          )}
        </div>
        <p className="mt-3 text-xs text-slate-600">
          Content is cached for 24 hours. Click refresh to fetch the latest {activeTab}.
        </p>
      </div>

      {/* Article Preview Modal */}
      {previewArticle && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
          onClick={handleCloseModal}
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
                    sourceColors[previewArticle.source] || 'bg-slate-600 text-slate-300'
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
                  onClick={handleCloseModal}
                  className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
                >
                  <X className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {/* Modal content */}
            <div className="overflow-y-auto max-h-[calc(90vh-140px)]">
              {/* Full-size thumbnail - hide in reader mode if we have content */}
              {previewArticle.thumbnail && !(readerModeEnabled && articleContent?.success) && (
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

                    {/* Success - Full article content */}
                    {articleContent?.success && articleContent.content && (
                      <div className="prose prose-invert prose-slate max-w-none">
                        {/* Render markdown content with headings, lists, and formatting */}
                        {/* Pass title to skip duplicate h1 that matches the article title */}
                        {renderMarkdown(articleContent.content, articleContent.title)}
                      </div>
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

            {/* Modal footer with action button */}
            <div className="p-4 border-t border-slate-700 flex justify-between items-center">
              <button
                onClick={handleCloseModal}
                className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
              >
                Close
              </button>
              <a
                href={previewArticle.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center space-x-2 px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-medium transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
                <span>Read on Website</span>
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
