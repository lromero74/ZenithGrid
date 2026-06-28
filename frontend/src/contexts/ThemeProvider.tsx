import { useState, useEffect, useCallback, useMemo, ReactNode } from 'react'
import { useBrand } from './BrandContext'
import { ThemeContext, type Theme } from './ThemeContext'

const STORAGE_KEY = 'btcbot-theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { brand, brandLoaded } = useBrand()

  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'neon' || stored === 'classic') return stored
    return 'classic' // safe default until brand loads
  })

  // Once brand loads, apply its default if user hasn't set a preference
  useEffect(() => {
    if (brandLoaded && !localStorage.getItem(STORAGE_KEY)) {
      setTheme(brand.defaultTheme)
    }
  }, [brandLoaded, brand.defaultTheme])

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('theme-neon', 'theme-classic')
    root.classList.add(`theme-${theme}`)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(prev => (prev === 'neon' ? 'classic' : 'neon'))
  }, [])

  const value = useMemo(() => ({ theme, toggleTheme }), [theme, toggleTheme])

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}
