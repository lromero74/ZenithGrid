import { useState } from 'react'
import { positionsApi, api } from '../../../services/api'

interface UsePositionMutationsProps {
  refetchPositions: () => void
}

export const usePositionMutations = ({ refetchPositions }: UsePositionMutationsProps) => {
  const [isProcessing, setIsProcessing] = useState(false)

  const handleClosePosition = async (closeConfirmPositionId: number | null) => {
    if (!closeConfirmPositionId) return

    setIsProcessing(true)
    try {
      const result = await positionsApi.close(closeConfirmPositionId)
      refetchPositions()
      // Show success notification
      alert(`Position closed successfully!\nProfit: ${result.profit_quote.toFixed(8)} (${result.profit_percentage.toFixed(2)}%)`)
      return { success: true }
    } catch (err: any) {
      alert(`Error closing position: ${err.response?.data?.detail || err.message}`)
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
      alert(`Error saving notes: ${err.response?.data?.detail || err.message}`)
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
      alert(`Error: ${err.response?.data?.detail || err.message}`)
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
