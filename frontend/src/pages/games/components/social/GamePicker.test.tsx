/**
 * Tests for GamePicker — searchable multiplayer game list for chat-to-game integration.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { GamePicker } from './GamePicker'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

describe('GamePicker', () => {
  const onSelect = vi.fn()
  const onClose = vi.fn()

  beforeEach(() => {
    onSelect.mockClear()
    onClose.mockClear()
  })

  it('renders search input', () => {
    render(<GamePicker memberCount={2} onSelect={onSelect} onClose={onClose} />)
    expect(screen.getByPlaceholderText(/search game/i)).toBeTruthy()
  })

  it('shows only multiplayer games', () => {
    render(<GamePicker memberCount={2} onSelect={onSelect} onClose={onClose} />)
    // Tic-Tac-Toe has multiplayer, should be visible
    expect(screen.getByText('Tic-Tac-Toe')).toBeTruthy()
  })

  it('filters games by search query', () => {
    render(<GamePicker memberCount={2} onSelect={onSelect} onClose={onClose} />)
    const input = screen.getByPlaceholderText(/search game/i)
    fireEvent.change(input, { target: { value: 'chess' } })
    expect(screen.getByText('Chess')).toBeTruthy()
    expect(screen.queryByText('Tic-Tac-Toe')).toBeNull()
  })

  it('calls onSelect when a game is clicked', () => {
    render(<GamePicker memberCount={2} onSelect={onSelect} onClose={onClose} />)
    const game = screen.getByText('Tic-Tac-Toe')
    fireEvent.click(game)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect.mock.calls[0][0].id).toBe('tic-tac-toe')
  })

  it('shows mode badges for each game', () => {
    render(<GamePicker memberCount={2} onSelect={onSelect} onClose={onClose} />)
    // Tic-Tac-Toe has vs and first_to_win modes
    expect(screen.getAllByText('VS').length).toBeGreaterThan(0)
  })
})
