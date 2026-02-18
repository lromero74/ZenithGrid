import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

export interface BrandConfig {
  name: string
  shortName: string
  tagline: string
  loginTitle: string
  loginTagline: string
  company: string
  companyLine: string
  copyright: string
  defaultTheme: 'neon' | 'classic'
  colors: {
    primary: string
    primaryHover: string
  }
  images: {
    loginBackground: string
  }
}

const DEFAULTS: BrandConfig = {
  name: 'Zenith Grid',
  shortName: 'Zenith Grid',
  tagline: 'Multi-Strategy Trading Platform',
  loginTitle: 'Zenith Grid',
  loginTagline: 'Multi-Strategy Trading Platform',
  company: '',
  companyLine: '',
  copyright: 'Zenith Grid',
  defaultTheme: 'classic',
  colors: { primary: '#3b82f6', primaryHover: '#2563eb' },
  images: { loginBackground: '' },
}

interface BrandContextValue {
  brand: BrandConfig
  brandLoaded: boolean
  brandImageUrl: (filename: string) => string
}

const BrandContext = createContext<BrandContextValue | undefined>(undefined)

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brand, setBrand] = useState<BrandConfig>(DEFAULTS)
  const [brandLoaded, setBrandLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/brand')
      .then(res => {
        if (!res.ok) throw new Error(`${res.status}`)
        return res.json()
      })
      .then(data => {
        if (!cancelled) {
          setBrand({ ...DEFAULTS, ...data, colors: { ...DEFAULTS.colors, ...data.colors }, images: { ...DEFAULTS.images, ...data.images } })
          setBrandLoaded(true)
        }
      })
      .catch(() => {
        if (!cancelled) setBrandLoaded(true)
      })
    return () => { cancelled = true }
  }, [])

  // Update browser tab title and inject brand colors when brand loads
  useEffect(() => {
    if (brandLoaded) {
      document.title = `${brand.shortName} - ${brand.tagline}`
    }
  }, [brandLoaded, brand.shortName, brand.tagline])

  const brandImageUrl = (filename: string) =>
    filename ? `/api/brand/images/${encodeURIComponent(filename)}` : ''

  return (
    <BrandContext.Provider value={{ brand, brandLoaded, brandImageUrl }}>
      {children}
    </BrandContext.Provider>
  )
}

export function useBrand() {
  const context = useContext(BrandContext)
  if (!context) {
    throw new Error('useBrand must be used within a BrandProvider')
  }
  return context
}
