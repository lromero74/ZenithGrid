/**
 * Type definitions for News page
 */

export interface NewsItem {
  id?: number  // DB article ID (for TTS caching)
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  summary: string | null
  thumbnail: string | null
  category: string
}

export interface VideoItem {
  title: string
  url: string
  video_id: string
  source: string
  source_name: string
  channel_name: string
  published: string | null
  thumbnail: string | null
  description: string | null
  category: string
}

export type NewsCategory =
  | 'CryptoCurrency'
  | 'Finance'
  | 'Business'
  | 'AI'
  | 'Technology'
  | 'Science'
  | 'Health'
  | 'World'
  | 'Nation'
  | 'Entertainment'
  | 'Sports'

export const NEWS_CATEGORIES: NewsCategory[] = [
  'CryptoCurrency',
  'Finance',
  'Business',
  'AI',
  'Technology',
  'Science',
  'Health',
  'World',
  'Nation',
  'Entertainment',
  'Sports',
]

export const CATEGORY_COLORS: Record<string, string> = {
  CryptoCurrency: 'bg-red-500/20 text-red-400 border-red-500/30',
  Finance: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  Business: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  AI: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  Technology: 'bg-lime-500/20 text-lime-400 border-lime-500/30',
  Science: 'bg-green-500/20 text-green-400 border-green-500/30',
  Health: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  World: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  Nation: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  Entertainment: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  Sports: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
}

export interface NewsSource {
  id: string
  name: string
  website: string
}

export interface VideoSource {
  id: string
  name: string
  website: string
  description: string
}

export interface NewsResponse {
  news: NewsItem[]
  sources: NewsSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
  page: number
  page_size: number
  total_pages: number
}

export interface VideoResponse {
  videos: VideoItem[]
  sources: VideoSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

export interface ArticleContentResponse {
  url: string
  title: string | null
  content: string | null
  author: string | null
  date: string | null
  success: boolean
  error: string | null
}

export type TabType = 'articles' | 'videos'
