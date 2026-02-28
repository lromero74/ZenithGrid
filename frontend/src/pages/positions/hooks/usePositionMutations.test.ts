/**
 * Tests for usePositionMutations hook
 *
 * Verifies close position (with slippage guard), save notes, cancel limit close,
 * add funds success callback, and error handling for all mutations.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePositionMutations } from './usePositionMutations'

// Mock the API module
vi.mock('../../../services/api', () => ({
  positionsApi: {
    close: vi.fn(),
  },
  api: {
    patch: vi.fn(),
    post: vi.fn(),
  },
}))

// Mock the NotificationContext
const mockAddToast = vi.fn()
vi.mock('../../../contexts/NotificationContext', () => ({
  useNotifications: () => ({
    addToast: mockAddToast,
  }),
}))

import { positionsApi, api } from '../../../services/api'

beforeEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePositionMutations initial state', () => {
  test('isProcessing is false initially', () => {
    const refetch = vi.fn()
    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    expect(result.current.isProcessing).toBe(false)
  })
})

describe('usePositionMutations handleClosePosition', () => {
  test('successfully closes a position and shows success toast', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockResolvedValue({
      message: 'Closed',
      profit_quote: 0.005,
      profit_percentage: 2.5,
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let closeResult: any
    await act(async () => {
      closeResult = await result.current.handleClosePosition(42)
    })

    expect(positionsApi.close).toHaveBeenCalledWith(42, false)
    expect(refetch).toHaveBeenCalled()
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'success', title: 'Position Closed' })
    )
    expect(closeResult).toEqual({ success: true })
    expect(result.current.isProcessing).toBe(false)
  })

  test('returns early when closeConfirmPositionId is null', async () => {
    const refetch = vi.fn()
    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    await act(async () => {
      await result.current.handleClosePosition(null)
    })

    expect(positionsApi.close).not.toHaveBeenCalled()
    expect(refetch).not.toHaveBeenCalled()
  })

  test('handles slippage guard block and returns slippageBlocked', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockResolvedValue({
      requires_confirmation: true,
      slippage_warning: 'Slippage too high: 5.2%',
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let closeResult: any
    await act(async () => {
      closeResult = await result.current.handleClosePosition(42)
    })

    expect(closeResult).toEqual({ success: false, slippageBlocked: true })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'Slippage Warning' })
    )
    expect(refetch).not.toHaveBeenCalled()
  })

  test('passes skipSlippageGuard flag when true', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockResolvedValue({
      message: 'Closed',
      profit_quote: 0.01,
      profit_percentage: 1.0,
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    await act(async () => {
      await result.current.handleClosePosition(42, true)
    })

    expect(positionsApi.close).toHaveBeenCalledWith(42, true)
  })

  test('handles close error and shows error toast', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockRejectedValue({
      message: 'Network error',
      response: { data: { detail: 'Position not found' } },
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let closeResult: any
    await act(async () => {
      closeResult = await result.current.handleClosePosition(42)
    })

    expect(closeResult).toEqual({ success: false })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'Close Failed', message: 'Position not found' })
    )
    expect(refetch).not.toHaveBeenCalled()
    expect(result.current.isProcessing).toBe(false)
  })

  test('falls back to err.message when response detail is absent', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockRejectedValue(new Error('Connection refused'))

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    await act(async () => {
      await result.current.handleClosePosition(42)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: 'Connection refused' })
    )
  })

  test('formats profit with correct decimal places in success toast', async () => {
    const refetch = vi.fn()
    vi.mocked(positionsApi.close).mockResolvedValue({
      message: 'Closed',
      profit_quote: 0.12345678,
      profit_percentage: 3.456,
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    await act(async () => {
      await result.current.handleClosePosition(10)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Profit: 0.12345678 (3.46%)',
      })
    )
  })
})

describe('usePositionMutations handleSaveNotes', () => {
  test('saves notes successfully', async () => {
    const refetch = vi.fn()
    vi.mocked(api.patch).mockResolvedValue({ data: {} })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let saveResult: any
    await act(async () => {
      saveResult = await result.current.handleSaveNotes(10, 'My position notes')
    })

    expect(api.patch).toHaveBeenCalledWith('/positions/10/notes', { notes: 'My position notes' })
    expect(refetch).toHaveBeenCalled()
    expect(saveResult).toEqual({ success: true })
  })

  test('returns early when editingNotesPositionId is null', async () => {
    const refetch = vi.fn()
    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    await act(async () => {
      await result.current.handleSaveNotes(null, 'notes')
    })

    expect(api.patch).not.toHaveBeenCalled()
  })

  test('shows error toast on save failure', async () => {
    const refetch = vi.fn()
    vi.mocked(api.patch).mockRejectedValue(new Error('Save failed'))

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let saveResult: any
    await act(async () => {
      saveResult = await result.current.handleSaveNotes(10, 'notes')
    })

    expect(saveResult).toEqual({ success: false })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'Save Failed' })
    )
  })
})

describe('usePositionMutations handleCancelLimitClose', () => {
  test('cancels limit close successfully', async () => {
    const refetch = vi.fn()
    vi.mocked(api.post).mockResolvedValue({ data: {} })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let cancelResult: any
    await act(async () => {
      cancelResult = await result.current.handleCancelLimitClose(5)
    })

    expect(api.post).toHaveBeenCalledWith('/positions/5/cancel-limit-close')
    expect(refetch).toHaveBeenCalled()
    expect(cancelResult).toEqual({ success: true })
  })

  test('shows error toast on cancel failure', async () => {
    const refetch = vi.fn()
    vi.mocked(api.post).mockRejectedValue({
      response: { data: { detail: 'No pending limit close' } },
    })

    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    let cancelResult: any
    await act(async () => {
      cancelResult = await result.current.handleCancelLimitClose(5)
    })

    expect(cancelResult).toEqual({ success: false })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'Error', message: 'No pending limit close' })
    )
    expect(refetch).not.toHaveBeenCalled()
  })
})

describe('usePositionMutations handleAddFundsSuccess', () => {
  test('calls refetchPositions', () => {
    const refetch = vi.fn()
    const { result } = renderHook(() =>
      usePositionMutations({ refetchPositions: refetch })
    )

    act(() => { result.current.handleAddFundsSuccess() })

    expect(refetch).toHaveBeenCalledTimes(1)
  })
})
