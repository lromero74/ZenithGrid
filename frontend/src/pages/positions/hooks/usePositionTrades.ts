import { useQuery } from '@tanstack/react-query'
import { positionsApi } from '../../../services/api'
import type { Position } from '../../../types'

interface UsePositionTradesProps {
  selectedPosition: number | null
  tradeHistoryPosition: Position | null
  showTradeHistoryModal: boolean
}

export const usePositionTrades = ({
  selectedPosition,
  tradeHistoryPosition,
  showTradeHistoryModal,
}: UsePositionTradesProps) => {
  // Fetch trades for selected position (expanded details)
  const { data: trades } = useQuery({
    queryKey: ['position-trades', selectedPosition],
    queryFn: () => positionsApi.getTrades(selectedPosition!),
    enabled: selectedPosition !== null,
  })

  // Fetch trade history for modal (separate from expanded details trades)
  const { data: tradeHistory, isLoading: isLoadingTradeHistory } = useQuery({
    queryKey: ['trade-history-modal', tradeHistoryPosition?.id],
    queryFn: () => positionsApi.getTrades(tradeHistoryPosition!.id),
    enabled: tradeHistoryPosition !== null && showTradeHistoryModal,
  })

  return {
    trades,
    tradeHistory,
    isLoadingTradeHistory,
  }
}
