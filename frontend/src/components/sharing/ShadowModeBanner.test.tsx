import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ShadowModeBanner } from './ShadowModeBanner'

describe('ShadowModeBanner', () => {
  it('renders the account name without owner name', () => {
    render(<ShadowModeBanner accountName="Louis Outlook" />)
    expect(screen.getByText(/Louis Outlook/)).toBeInTheDocument()
  })

  it('indicates shadow / read-only mode', () => {
    render(<ShadowModeBanner accountName="Test Account" />)
    expect(screen.getByText(/shadow/i)).toBeInTheDocument()
    expect(screen.getByText(/read.only/i)).toBeInTheDocument()
  })

  it('shows owner display name when provided', () => {
    render(<ShadowModeBanner accountName="Main Trading" ownerName="Louis" />)
    expect(screen.getByText(/Louis's account "Main Trading"/)).toBeInTheDocument()
  })

  it('falls back to account-only label when ownerName is null', () => {
    render(<ShadowModeBanner accountName="Main Trading" ownerName={null} />)
    expect(screen.getByText(/Viewing Main Trading/)).toBeInTheDocument()
    expect(screen.queryByText(/account "/)).not.toBeInTheDocument()
  })
})
