import { useState, useEffect, useCallback, useMemo, ReactNode } from 'react'
import { BrandContext, type BrandConfig } from './BrandContext'

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

  const brandImageUrl = useCallback((filename: string) =>
    filename ? `/api/brand/images/${encodeURIComponent(filename)}` : '', [])

  const value = useMemo(
    () => ({ brand, brandLoaded, brandImageUrl }),
    [brand, brandLoaded, brandImageUrl]
  )

  return (
    <BrandContext.Provider value={value}>
      {children}
    </BrandContext.Provider>
  )
}
