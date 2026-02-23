import { useMutation, useQueryClient } from '@tanstack/react-query'
import { botsApi } from '../../../services/api'
import type { Bot, BotCreate } from '../../../types'
import { useNotifications } from '../../../contexts/NotificationContext'

interface UseBotMutationsProps {
  selectedAccount: { id: number } | null
  bots: Bot[] | undefined
  setShowModal: (show: boolean) => void
  resetForm: () => void
  onCloneSuccess?: (clonedBot: Bot) => void
  projectionTimeframe?: string
}

export function useBotMutations({
  selectedAccount,
  bots,
  setShowModal,
  resetForm,
  onCloneSuccess,
  projectionTimeframe
}: UseBotMutationsProps) {
  const queryClient = useQueryClient()
  const { addToast } = useNotifications()

  // Create bot mutation
  const createBot = useMutation({
    mutationFn: (data: BotCreate) => botsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      setShowModal(false)
      resetForm()
    },
    onError: (error: Error & { response?: { data?: { detail?: string | Array<{ msg: string; loc: string[] }> } } }) => {
      const detail = error.response?.data?.detail
      let message = 'Failed to create bot'
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail)) {
        message = detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ')
      } else if (error.message) {
        message = error.message
      }
      addToast({ type: 'error', title: 'Create Bot Failed', message })
      console.error('Create bot error:', error)
    },
  })

  // Update bot mutation
  const updateBot = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BotCreate> }) =>
      botsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      setShowModal(false)
      resetForm()
    },
    onError: (error: Error & { response?: { data?: { detail?: string | Array<{ msg: string; loc: string[] }> } } }) => {
      const detail = error.response?.data?.detail
      let message = 'Failed to update bot'
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail)) {
        message = detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ')
      } else if (error.message) {
        message = error.message
      }
      addToast({ type: 'error', title: 'Update Bot Failed', message })
      console.error('Update bot error:', error)
    },
  })

  // Delete bot mutation
  const deleteBot = useMutation({
    mutationFn: (id: number) => botsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Start bot mutation with optimistic update
  const startBot = useMutation({
    mutationFn: (id: number) => botsApi.start(id),
    onMutate: async (id) => {
      // Cancel all bot queries to prevent overwrites
      await queryClient.cancelQueries({ queryKey: ['bots'] })
      // Update all matching bot query cache entries optimistically
      const queryKey = ['bots', selectedAccount?.id, projectionTimeframe]
      const previousBots = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old: Bot[] | undefined) =>
        old?.map(bot => bot.id === id ? { ...bot, is_active: true } : bot)
      )
      return { previousBots, queryKey }
    },
    onError: (_err, _id, context) => {
      if (context?.queryKey) {
        queryClient.setQueryData(context.queryKey, context.previousBots)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Stop bot mutation with optimistic update
  const stopBot = useMutation({
    mutationFn: (id: number) => botsApi.stop(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['bots'] })
      const queryKey = ['bots', selectedAccount?.id, projectionTimeframe]
      const previousBots = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old: Bot[] | undefined) =>
        old?.map(bot => bot.id === id ? { ...bot, is_active: false } : bot)
      )
      return { previousBots, queryKey }
    },
    onError: (_err, _id, context) => {
      if (context?.queryKey) {
        queryClient.setQueryData(context.queryKey, context.previousBots)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Clone bot mutation
  const cloneBot = useMutation({
    mutationFn: (id: number) => botsApi.clone(id),
    onSuccess: (clonedBot) => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      // Open the cloned bot in edit modal if callback provided
      if (onCloneSuccess) {
        onCloneSuccess(clonedBot)
      }
    },
  })

  // Copy to account mutation (live <-> paper trading)
  const copyToAccount = useMutation({
    mutationFn: ({ id, targetAccountId }: { id: number; targetAccountId: number }) =>
      botsApi.copyToAccount(id, targetAccountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Force run mutation
  const forceRunBot = useMutation({
    mutationFn: (id: number) => botsApi.forceRun(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Cancel all positions mutation
  const cancelAllPositions = useMutation({
    mutationFn: (id: number) => botsApi.cancelAllPositions(id, true),
    onSuccess: (data, botId) => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      queryClient.invalidateQueries({ queryKey: ['positions'] })

      const bot = bots?.find(b => b.id === botId)
      const botName = bot?.name || `Bot #${botId}`

      if (data.failed_count > 0) {
        addToast({ type: 'error', title: 'Partial Cancellation', message: `Cancelled ${data.cancelled_count} of ${data.cancelled_count + data.failed_count} positions for ${botName}. ${data.errors.length} errors.` })
      } else {
        addToast({ type: 'success', title: 'Positions Cancelled', message: `Cancelled all ${data.cancelled_count} positions for ${botName}` })
      }
    },
  })

  // Sell all positions mutation
  const sellAllPositions = useMutation({
    mutationFn: (id: number) => botsApi.sellAllPositions(id, true),
    onSuccess: (data, botId) => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      queryClient.invalidateQueries({ queryKey: ['positions'] })

      const bot = bots?.find(b => b.id === botId)
      const botName = bot?.name || `Bot #${botId}`

      if (data.failed_count > 0) {
        addToast({ type: 'error', title: 'Partial Sell', message: `Sold ${data.sold_count} of ${data.sold_count + data.failed_count} positions for ${botName}. Profit: ${data.total_profit_quote.toFixed(8)}` })
      } else {
        addToast({ type: 'success', title: 'All Positions Sold', message: `Sold all ${data.sold_count} positions for ${botName}. Profit: ${data.total_profit_quote.toFixed(8)}` })
      }
    },
  })

  return {
    createBot,
    updateBot,
    deleteBot,
    startBot,
    stopBot,
    cloneBot,
    copyToAccount,
    forceRunBot,
    cancelAllPositions,
    sellAllPositions
  }
}
