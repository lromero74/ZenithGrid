import { useState } from 'react'
import { positionsApi, api } from '../../../services/api'
import { useNotifications } from '../../../contexts/NotificationContext'

interface UsePositionMutationsProps {
  refetchPositions: () => void
}

export const usePositionMutations = ({ refetchPositions }: UsePositionMutationsProps) => {
  const [isProcessing, setIsProcessing] = useState(false)
  const { addToast } = useNotifications()

  const handleClosePosition = async (closeConfirmPositionId: number | null, skipSlippageGuard = false) => {
    if (!closeConfirmPositionId) return

    setIsProcessing(true)
    try {
      const result = await positionsApi.close(closeConfirmPositionId, skipSlippageGuard)
      if (result.requires_confirmation) {
        // Inline slippage guard blocked the close — show warning as toast
        addToast({ type: 'error', title: 'Slippage Warning', message: result.slippage_warning || 'High slippage detected — use slippage check first' })
        return { success: false, slippageBlocked: true }
      }
      refetchPositions()
      addToast({ type: 'success', title: 'Position Closed', message: `Profit: ${(result.profit_quote ?? 0).toFixed(8)} (${(result.profit_percentage ?? 0).toFixed(2)}%)` })
      return { success: true }
    } catch (err: any) {
      addToast({ type: 'error', title: 'Close Failed', message: err.response?.data?.detail || err.message })
      return { success: false }
    } finally {
      setIsProcessing(false)
    }
  }

  const handleAddFundsSuccess = () => {
    refetchPositions()
  }

  const handleSaveNotes = async (editingNotesPositionId: number | null, notesText: string) => {
    if (!editingNotesPositionId) return

    setIsProcessing(true)
    try {
      await api.patch(`/positions/${editingNotesPositionId}/notes`, {
        notes: notesText
      })
      refetchPositions()
      return { success: true }
    } catch (err: any) {
      addToast({ type: 'error', title: 'Save Failed', message: err.response?.data?.detail || err.message })
      return { success: false }
    } finally {
      setIsProcessing(false)
    }
  }

  const handleCancelLimitClose = async (positionId: number) => {
    try {
      await api.post(`/positions/${positionId}/cancel-limit-close`)
      refetchPositions()
      return { success: true }
    } catch (err: any) {
      addToast({ type: 'error', title: 'Error', message: err.response?.data?.detail || err.message })
      return { success: false }
    }
  }

  return {
    isProcessing,
    handleClosePosition,
    handleAddFundsSuccess,
    handleSaveNotes,
    handleCancelLimitClose,
  }
}
