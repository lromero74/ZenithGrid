import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ObserverModeBanner } from './ObserverModeBanner'

describe('ObserverModeBanner', () => {
  it('renders the account name without owner name', () => {
    render(<ObserverModeBanner accountName="Louis Outlook" />)
    expect(screen.getByText(/Louis Outlook/)).toBeInTheDocument()
  })

  it('indicates observer / read-only mode', () => {
    render(<ObserverModeBanner accountName="Test Account" />)
    expect(screen.getByText(/observer/i)).toBeInTheDocument()
    expect(screen.getByText(/read.only/i)).toBeInTheDocument()
  })

  it('shows owner display name when provided', () => {
    render(<ObserverModeBanner accountName="Main Trading" ownerName="Louis" />)
    expect(screen.getByText(/Louis's account "Main Trading"/)).toBeInTheDocument()
  })

  it('falls back to account-only label when ownerName is null', () => {
    render(<ObserverModeBanner accountName="Main Trading" ownerName={null} />)
    expect(screen.getByText(/Viewing Main Trading/)).toBeInTheDocument()
    expect(screen.queryByText(/account "/)).not.toBeInTheDocument()
  })
})
