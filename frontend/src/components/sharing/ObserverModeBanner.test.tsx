import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ObserverModeBanner } from './ObserverModeBanner'

describe('ObserverModeBanner', () => {
  it('renders the account name', () => {
    render(<ObserverModeBanner accountName="Louis Outlook" />)
    expect(screen.getByText(/Louis Outlook/)).toBeInTheDocument()
  })

  it('indicates observer / read-only mode', () => {
    render(<ObserverModeBanner accountName="Test Account" />)
    expect(screen.getByText(/observer/i)).toBeInTheDocument()
    expect(screen.getByText(/read.only/i)).toBeInTheDocument()
  })
})
