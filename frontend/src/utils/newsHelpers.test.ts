/**
 * Tests for utils/newsHelpers.ts
 *
 * Tests markdownToPlainText and scrollToArticle independently from the
 * news page re-exports. Focuses on edge cases not covered elsewhere.
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { markdownToPlainText, scrollToArticle } from './newsHelpers'

describe('markdownToPlainText', () => {
  test('handles deeply nested formatting', () => {
    // Bold italic combo
    expect(markdownToPlainText('***bold italic***')).toBe('bold italic')
    expect(markdownToPlainText('___bold italic___')).toBe('bold italic')
  })

  test('handles multiple links in one line', () => {
    const md = 'Visit [Google](https://google.com) and [GitHub](https://github.com)'
    expect(markdownToPlainText(md)).toBe('Visit Google and GitHub')
  })

  test('handles multiple bold segments in one line', () => {
    const md = '**first** normal **second**'
    expect(markdownToPlainText(md)).toBe('first normal second')
  })

  test('handles image followed by text', () => {
    const md = '![logo](img.png) Some description'
    expect(markdownToPlainText(md)).toBe('logo Some description')
  })

  test('handles code block with language spec', () => {
    const md = 'text\n```python\nprint("hello")\n```\nmore text'
    expect(markdownToPlainText(md)).toBe('text\n\nmore text')
  })

  test('handles multiple inline code segments', () => {
    const md = 'use `foo` and `bar`'
    expect(markdownToPlainText(md)).toBe('use foo and bar')
  })

  test('removes self-closing HTML tags', () => {
    expect(markdownToPlainText('text<br/>more')).toBe('textmore')
    expect(markdownToPlainText('text<hr>more')).toBe('textmore')
  })

  test('handles unordered list with plus marker', () => {
    expect(markdownToPlainText('+ item one\n+ item two')).toBe('item one\nitem two')
  })

  test('handles unordered list with asterisk marker', () => {
    expect(markdownToPlainText('* item one\n* item two')).toBe('item one\nitem two')
  })

  test('handles heading levels 1-6', () => {
    expect(markdownToPlainText('# H1')).toBe('H1')
    expect(markdownToPlainText('## H2')).toBe('H2')
    expect(markdownToPlainText('### H3')).toBe('H3')
    expect(markdownToPlainText('#### H4')).toBe('H4')
    expect(markdownToPlainText('##### H5')).toBe('H5')
    expect(markdownToPlainText('###### H6')).toBe('H6')
  })

  test('handles underscore italic', () => {
    expect(markdownToPlainText('_italic text_')).toBe('italic text')
  })

  test('handles underscore bold', () => {
    expect(markdownToPlainText('__bold text__')).toBe('bold text')
  })

  test('preserves normal text without formatting', () => {
    expect(markdownToPlainText('Just some normal text here.')).toBe('Just some normal text here.')
  })

  test('handles complex real-world article', () => {
    const md = [
      '# Breaking News',
      '',
      'Bitcoin has **surged** past $100k according to [CoinDesk](https://coindesk.com).',
      '',
      '## Key Points',
      '',
      '- ETF inflows hit record',
      '- Institutional adoption grows',
      '',
      '> This is historic',
      '',
      '---',
      '',
      '*Stay tuned for updates.*',
    ].join('\n')

    const result = markdownToPlainText(md)
    expect(result).toContain('Breaking News')
    expect(result).toContain('surged')
    expect(result).toContain('CoinDesk')
    expect(result).toContain('ETF inflows hit record')
    expect(result).toContain('This is historic')
    expect(result).toContain('Stay tuned for updates.')
    expect(result).not.toContain('**')
    expect(result).not.toContain('[')
    expect(result).not.toContain('](')
    expect(result).not.toContain('#')
    expect(result).not.toContain('---')
    expect(result).not.toContain('>')
    expect(result).not.toContain('*')
  })
})

describe('scrollToArticle', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('scrolls to article element by data-article-url', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/test')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/test')
    expect(el.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  })

  test('does not throw when element is not found', () => {
    scrollToArticle('https://nonexistent.com')
  })

  test('adds and removes pulse animation after 3 seconds', () => {
    vi.useFakeTimers()
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/pulse')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/pulse', true)
    expect(el.classList.contains('animate-pulse-ring')).toBe(true)

    vi.advanceTimersByTime(3000)
    expect(el.classList.contains('animate-pulse-ring')).toBe(false)
  })

  test('does not add pulse when addPulse is false', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/nopulse')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/nopulse', false)
    expect(el.classList.contains('animate-pulse-ring')).toBe(false)
  })

  test('does not add pulse by default', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/default')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/default')
    expect(el.classList.contains('animate-pulse-ring')).toBe(false)
  })
})
