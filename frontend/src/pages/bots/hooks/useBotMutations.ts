import { useMutation, useQueryClient } from '@tanstack/react-query'
import { botsApi } from '../../../services/api'
import type { Bot, BotCreate } from '../../../types'

interface UseBotMutationsProps {
  selectedAccount: { id: number } | null
  bots: Bot[] | undefined
  setShowModal: (show: boolean) => void
  resetForm: () => void
}

export function useBotMutations({
  selectedAccount,
  bots,
  setShowModal,
  resetForm
}: UseBotMutationsProps) {
  const queryClient = useQueryClient()

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
      alert(`Error: ${message}`)
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
      alert(`Error: ${message}`)
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
      const queryKey = ['bots', selectedAccount?.id]
      await queryClient.cancelQueries({ queryKey })
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
      const queryKey = ['bots', selectedAccount?.id]
      await queryClient.cancelQueries({ queryKey })
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
        alert(
          `Cancelled ${data.cancelled_count} of ${data.cancelled_count + data.failed_count} positions for ${botName}.\n\n` +
          `Errors:\n${data.errors.join('\n')}`
        )
      } else {
        alert(`✅ Successfully cancelled all ${data.cancelled_count} positions for ${botName}`)
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
        alert(
          `Sold ${data.sold_count} of ${data.sold_count + data.failed_count} positions for ${botName}.\n\n` +
          `Total Profit: ${data.total_profit_quote.toFixed(8)}\n\n` +
          `Errors:\n${data.errors.join('\n')}`
        )
      } else {
        alert(
          `✅ Successfully sold all ${data.sold_count} positions for ${botName}\n` +
          `Total Profit: ${data.total_profit_quote.toFixed(8)}`
        )
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
    forceRunBot,
    cancelAllPositions,
    sellAllPositions
  }
}
