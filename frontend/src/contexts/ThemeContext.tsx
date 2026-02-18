import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useBrand } from './BrandContext'

type Theme = 'neon' | 'classic'

interface ThemeContextValue {
  theme: Theme
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

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

  const toggleTheme = () => {
    setTheme(prev => (prev === 'neon' ? 'classic' : 'neon'))
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
