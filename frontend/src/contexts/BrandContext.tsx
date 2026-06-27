import { createContext, useContext } from 'react'

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

export interface BrandContextValue {
  brand: BrandConfig
  brandLoaded: boolean
  brandImageUrl: (filename: string) => string
}

export const BrandContext = createContext<BrandContextValue | undefined>(undefined)

export function useBrand() {
  const context = useContext(BrandContext)
  if (!context) {
    throw new Error('useBrand must be used within a BrandProvider')
  }
  return context
}
