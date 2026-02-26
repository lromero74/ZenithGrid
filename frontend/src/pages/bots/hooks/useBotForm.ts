import { useState, useEffect, useCallback } from 'react'
import { useNotifications } from '../../../contexts/NotificationContext'
import type { Bot, StrategyParameter } from '../../../types'
import { blacklistApi, BlacklistEntry } from '../../../services/api'
import type {
  BotFormData,
  ValidationError,
} from '../../../components/bots'

interface UseBotFormProps {
  showModal: boolean
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  editingBot: Bot | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  templates: any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategies: any[]
  validationErrors: ValidationError[]
  selectedAccount: {
    id: number
    name: string
    type?: string
    chain_id?: number
  } | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBot: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  updateBot: any
}

interface CoinCategoryData {
  coinCategories: Record<string, string>
  categoryCounts: Record<string, number>
  overriddenCoins: Set<string>
}

export function useBotForm({
  showModal,
  formData,
  setFormData,
  editingBot,
  templates,
  strategies,
  validationErrors,
  selectedAccount,
  createBot,
  updateBot,
}: UseBotFormProps) {
  const { addToast } = useNotifications()

  // Coin category state
  const [coinCategories, setCoinCategories] =
    useState<Record<string, string>>({})
  const [categoryCounts, setCategoryCounts] =
    useState<Record<string, number>>({
      APPROVED: 0,
      BORDERLINE: 0,
      QUESTIONABLE: 0,
      MEME: 0,
      BLACKLISTED: 0,
    })
  const [overriddenCoins, setOverriddenCoins] =
    useState<Set<string>>(new Set())

  // Fetch blacklist/category data for badges and counts
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const blacklist = await blacklistApi.getAll()
        const categoryMap: Record<string, string> = {}
        const overridden = new Set<string>()
        const counts: Record<string, number> = {
          APPROVED: 0,
          BORDERLINE: 0,
          QUESTIONABLE: 0,
          MEME: 0,
          BLACKLISTED: 0,
        }

        blacklist.forEach((entry: BlacklistEntry) => {
          const reason = entry.reason || ''
          let globalCategory = 'BLACKLISTED'

          if (reason.startsWith('[APPROVED]'))
            globalCategory = 'APPROVED'
          else if (reason.startsWith('[BORDERLINE]'))
            globalCategory = 'BORDERLINE'
          else if (reason.startsWith('[QUESTIONABLE]'))
            globalCategory = 'QUESTIONABLE'
          else if (reason.startsWith('[MEME]'))
            globalCategory = 'MEME'

          const effectiveCategory =
            entry.user_override_category || globalCategory
          categoryMap[entry.symbol] = effectiveCategory

          if (entry.user_override_category) {
            overridden.add(entry.symbol)
          }

          counts[effectiveCategory]++
        })

        setCoinCategories(categoryMap)
        setCategoryCounts(counts)
        setOverriddenCoins(overridden)
      } catch (err) {
        console.error('Failed to load coin categories:', err)
      }
    }

    if (showModal) {
      fetchCategories()
    }
  }, [showModal])

  const loadTemplate = useCallback((templateId: number) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const template = templates.find((t: any) => t.id === templateId)
    if (!template) return

    setFormData({
      name: `${template.name} (Copy)`,
      description: template.description || '',
      market_type: template.market_type || 'spot',
      strategy_type: template.strategy_type,
      product_id: template.product_ids?.[0] || 'ETH-BTC',
      product_ids: template.product_ids || [],
      split_budget_across_pairs:
        template.split_budget_across_pairs || false,
      reserved_btc_balance:
        template.reserved_btc_balance || 0,
      reserved_usd_balance:
        template.reserved_usd_balance || 0,
      budget_percentage: template.budget_percentage || 0,
      check_interval_seconds:
        template.check_interval_seconds || 300,
      strategy_config: template.strategy_config,
      exchange_type: template.exchange_type || 'cex',
    })
  }, [templates, setFormData])

  const handleStrategyChange = useCallback(
    (strategyType: string) => {
      const strategy = strategies.find(
        (s) => s.id === strategyType
      )
      if (!strategy) return

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const config: Record<string, any> = {}
      strategy.parameters.forEach(
        (param: StrategyParameter) => {
          config[param.name] = param.default
        }
      )

      setFormData({
        ...formData,
        strategy_type: strategyType,
        strategy_config: config,
      })
    },
    [strategies, formData, setFormData]
  )

  const handleParamChange = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (paramName: string, value: any) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const updates: Record<string, any> = {
        [paramName]: value,
      }

      // When max_concurrent_deals changes, cap
      // max_simultaneous_same_pair
      if (paramName === 'max_concurrent_deals') {
        const maxSim =
          formData.strategy_config
            .max_simultaneous_same_pair || 1
        if (maxSim > value) {
          updates.max_simultaneous_same_pair = value
        }
      }
      // When max_simultaneous_same_pair changes, cap at
      // max_concurrent_deals
      if (paramName === 'max_simultaneous_same_pair') {
        const maxDeals =
          formData.strategy_config.max_concurrent_deals || 1
        if (value > maxDeals) {
          updates.max_simultaneous_same_pair = maxDeals
        }
      }

      setFormData({
        ...formData,
        strategy_config: {
          ...formData.strategy_config,
          ...updates,
        },
      })
    },
    [formData, setFormData]
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()

      if (validationErrors.length > 0) {
        addToast({
          type: 'error',
          title: 'Validation Error',
          message:
            'Order values are below exchange minimum. ' +
            'Increase percentage values or fund your account.',
        })
        return
      }

      if (!selectedAccount?.id && !editingBot) {
        addToast({
          type: 'error',
          title: 'No Account',
          message:
            'Please select an account before creating a bot',
        })
        return
      }

      if (formData.product_ids.length === 0) {
        addToast({
          type: 'error',
          title: 'No Pair Selected',
          message:
            'Please select at least one trading pair',
        })
        return
      }

      const check_interval_seconds =
        formData.check_interval_seconds ?? 300
      const reserved_btc_balance =
        formData.reserved_btc_balance ?? 0
      const reserved_usd_balance =
        formData.reserved_usd_balance ?? 0
      const budget_percentage =
        formData.budget_percentage ?? 0

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const botData: any = {
        name: formData.name,
        description: formData.description || undefined,
        account_id:
          selectedAccount?.id ?? editingBot?.account_id,
        market_type: formData.market_type || 'spot',
        strategy_type: formData.strategy_type,
        product_id: formData.product_ids[0],
        product_ids: formData.product_ids,
        split_budget_across_pairs:
          formData.split_budget_across_pairs,
        reserved_btc_balance,
        reserved_usd_balance,
        budget_percentage,
        check_interval_seconds,
        strategy_config: formData.strategy_config,
        exchange_type: formData.exchange_type,
        chain_id: formData.chain_id,
        dex_router: formData.dex_router,
        wallet_private_key: formData.wallet_private_key,
        rpc_url: formData.rpc_url,
      }

      if (editingBot) {
        updateBot.mutate({
          id: editingBot.id,
          data: botData,
        })
      } else {
        createBot.mutate(botData)
      }
    },
    [
      formData,
      validationErrors,
      selectedAccount,
      editingBot,
      createBot,
      updateBot,
      addToast,
    ]
  )

  const coinCategoryData: CoinCategoryData = {
    coinCategories,
    categoryCounts,
    overriddenCoins,
  }

  return {
    coinCategoryData,
    loadTemplate,
    handleStrategyChange,
    handleParamChange,
    handleSubmit,
  }
}

export type { CoinCategoryData }
