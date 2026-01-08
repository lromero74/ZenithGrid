/**
 * Type definitions for News page
 */

export interface NewsItem {
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  summary: string | null
  thumbnail: string | null
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
