import { useState } from 'react'
import { positionsApi, api } from '../../../services/api'
import { useNotifications } from '../../../contexts/NotificationContext'
import { getApiErrorMessage } from '../../../utils/apiError'

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
        // Inline slippage guard blocked the close — return warning so caller can show confirm dialog
        return { success: false, slippageBlocked: true, slippageWarning: result.slippage_warning }
      }
      refetchPositions()
      addToast({ type: 'success', title: 'Position Closed', message: `Profit: ${(result.profit_quote ?? 0).toFixed(8)} (${(result.profit_percentage ?? 0).toFixed(2)}%)` })
      return { success: true }
    } catch (err) {
      addToast({ type: 'error', title: 'Close Failed', message: getApiErrorMessage(err, err instanceof Error ? err.message : 'Operation failed') })
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
    } catch (err) {
      addToast({ type: 'error', title: 'Save Failed', message: getApiErrorMessage(err, err instanceof Error ? err.message : 'Operation failed') })
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
    } catch (err) {
      addToast({ type: 'error', title: 'Error', message: getApiErrorMessage(err, err instanceof Error ? err.message : 'Operation failed') })
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
