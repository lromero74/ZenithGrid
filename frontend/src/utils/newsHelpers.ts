/**
 * Shared news helper utilities.
 *
 * Functions used by components outside the News page live here to avoid
 * components/ importing from pages/ (inverted dependency).
 */

/**
 * Convert markdown to plain text for TTS.
 * Strips all markdown formatting while preserving readable content.
 */
export const markdownToPlainText = (markdown: string): string => {
  let text = markdown

  // Remove code blocks (``` ... ```)
  text = text.replace(/```[\s\S]*?```/g, '')

  // Remove inline code (`code`)
  text = text.replace(/`([^`]+)`/g, '$1')

  // Remove images ![alt](url)
  text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')

  // Convert links [text](url) to just text
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')

  // Remove heading markers (# ## ### etc) but keep the text
  text = text.replace(/^#{1,6}\s+/gm, '')

  // Remove stray # characters that aren't proper headings (artifacts like "Sponsored##")
  text = text.replace(/#{2,}/g, '')

  // Remove common promotional/ad artifacts that slip through content extraction
  // Handle concatenated cases like "SponsoredCustomers" -> "Customers"
  text = text.replace(/\bSponsored(?=[A-Z])/g, '')
  text = text.replace(/\bAdvertisement(?=[A-Z])/g, '')
  text = text.replace(/\bPromoted(?=[A-Z])/g, '')
  // Handle standalone cases at line boundaries
  text = text.replace(/\b(Sponsored|Advertisement|Promoted|Ad)\s*$/gim, '')
  text = text.replace(/^\s*(Sponsored|Advertisement|Promoted|Ad)\b/gim, '')

  // Remove bold/italic markers
  text = text.replace(/\*\*\*([^*]+)\*\*\*/g, '$1')  // ***bold italic***
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1')      // **bold**
  text = text.replace(/\*([^*]+)\*/g, '$1')          // *italic*
  text = text.replace(/___([^_]+)___/g, '$1')        // ___bold italic___
  text = text.replace(/__([^_]+)__/g, '$1')          // __bold__
  text = text.replace(/_([^_]+)_/g, '$1')            // _italic_

  // Remove horizontal rules
  text = text.replace(/^[-*_]{3,}\s*$/gm, '')

  // Remove blockquote markers
  text = text.replace(/^>\s+/gm, '')

  // Remove list markers (-, *, +, 1., 2., etc)
  text = text.replace(/^[\s]*[-*+]\s+/gm, '')
  text = text.replace(/^[\s]*\d+\.\s+/gm, '')

  // Remove HTML tags if any
  text = text.replace(/<[^>]+>/g, '')

  // Collapse multiple newlines into double newline (paragraph break)
  text = text.replace(/\n{3,}/g, '\n\n')

  // Collapse multiple spaces
  text = text.replace(/[ \t]+/g, ' ')

  // Trim each line
  text = text.split('\n').map(line => line.trim()).join('\n')

  // Final trim
  return text.trim()
}

/**
 * Scroll to an article element by data attribute with smooth animation.
 */
export const scrollToArticle = (articleUrl: string, addPulse = false): void => {
  const element = document.querySelector(`[data-article-url="${CSS.escape(articleUrl)}"]`)
  if (!element) return

  element.scrollIntoView({ behavior: 'smooth', block: 'center' })

  if (addPulse) {
    element.classList.add('animate-pulse-ring')
    setTimeout(() => {
      element.classList.remove('animate-pulse-ring')
    }, 3000)
  }
}
