import type { BotFormData } from '../../../components/bots'
import type { CoinCategoryData } from '../hooks/useBotForm'

interface CategoryBadgeProps {
  pairId: string
  coinCategoryData: CoinCategoryData
}

/**
 * Renders a small colored badge (A/B/Q/M/X) indicating
 * the coin's category. Shows an asterisk for user
 * overrides.
 */
export function CategoryBadge({
  pairId,
  coinCategoryData,
}: CategoryBadgeProps) {
  const { coinCategories, overriddenCoins } =
    coinCategoryData
  const baseCurrency = pairId.split('-')[0]
  const category =
    coinCategories[baseCurrency] || 'APPROVED'
  const isOverridden = overriddenCoins.has(baseCurrency)

  const badgeStyles: Record<
    string,
    { bg: string; text: string; label: string }
  > = {
    APPROVED: {
      bg: 'bg-green-600/20',
      text: 'text-green-400',
      label: 'A',
    },
    BORDERLINE: {
      bg: 'bg-yellow-600/20',
      text: 'text-yellow-400',
      label: 'B',
    },
    QUESTIONABLE: {
      bg: 'bg-orange-600/20',
      text: 'text-orange-400',
      label: 'Q',
    },
    MEME: {
      bg: 'bg-purple-600/20',
      text: 'text-purple-400',
      label: 'M',
    },
    BLACKLISTED: {
      bg: 'bg-red-600/20',
      text: 'text-red-400',
      label: 'X',
    },
  }

  const style = badgeStyles[category]
  return (
    <span
      className={`inline-flex items-center justify-center ${isOverridden ? 'w-6' : 'w-4'} h-4 text-[10px] font-bold rounded ${style.bg} ${style.text}`}
      title={
        isOverridden
          ? `${category} (personal override)`
          : category
      }
    >
      {style.label}
      {isOverridden ? '*' : ''}
    </span>
  )
}

interface CoinCategorySelectorProps {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  coinCategoryData: CoinCategoryData
}

/**
 * Renders the Allowed Coin Categories section with
 * checkboxes for each category (APPROVED, BORDERLINE,
 * QUESTIONABLE, MEME, BLACKLISTED) plus the
 * Max Synthetic Candles % input.
 */
export function CoinCategorySelector({
  formData,
  setFormData,
  coinCategoryData,
}: CoinCategorySelectorProps) {
  const { categoryCounts } = coinCategoryData
  const allowedCategories =
    formData.strategy_config?.allowed_categories || [
      'APPROVED',
      'BORDERLINE',
    ]

  const categories = [
    {
      value: 'APPROVED',
      label: 'Approved',
      description: 'Strong fundamentals, clear utility',
      color: 'green' as const,
    },
    {
      value: 'BORDERLINE',
      label: 'Borderline',
      description:
        'Some concerns, declining relevance',
      color: 'yellow' as const,
    },
    {
      value: 'QUESTIONABLE',
      label: 'Questionable',
      description:
        'Significant red flags, unclear utility',
      color: 'orange' as const,
    },
    {
      value: 'MEME',
      label: 'Meme Coins',
      description:
        'Community-driven, high volatility',
      color: 'purple' as const,
    },
    {
      value: 'BLACKLISTED',
      label: 'Blacklisted',
      description: 'Scams, abandoned projects',
      color: 'red' as const,
    },
  ]

  const colorClasses = {
    green: 'border-green-600 bg-green-950/30',
    yellow: 'border-yellow-600 bg-yellow-950/30',
    orange: 'border-orange-600 bg-orange-950/30',
    purple: 'border-purple-600 bg-purple-950/30',
    red: 'border-red-600 bg-red-950/30',
  }

  const handleCategoryToggle = (
    categoryValue: string,
    isChecked: boolean
  ) => {
    const currentCategories =
      formData.strategy_config?.allowed_categories || [
        'APPROVED',
        'BORDERLINE',
      ]
    const newCategories = isChecked
      ? [...currentCategories, categoryValue]
      : currentCategories.filter(
          (c: string) => c !== categoryValue
        )

    setFormData({
      ...formData,
      strategy_config: {
        ...formData.strategy_config,
        allowed_categories: newCategories,
      },
    })
  }

  return (
    <>
      {/* Allowed Categories */}
      <div className="mt-4 pt-4 border-t border-slate-600">
        <label className="block text-sm font-medium text-slate-300 mb-3">
          Allowed Coin Categories
          <span className="text-xs text-slate-400 font-normal ml-2">
            (Select which types of coins this bot can
            trade)
          </span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {categories.map((category) => {
            const isChecked = allowedCategories.includes(
              category.value
            )
            return (
              <label
                key={category.value}
                className={`flex items-start gap-3 p-3 rounded border-2 cursor-pointer transition-all ${
                  isChecked
                    ? colorClasses[category.color]
                    : 'border-slate-600 bg-slate-700/50 opacity-60'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={(e) =>
                    handleCategoryToggle(
                      category.value,
                      e.target.checked
                    )
                  }
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-slate-200">
                    {category.label}
                    <span className="text-xs text-slate-400 font-normal ml-1.5">
                      (
                      {categoryCounts[category.value] ||
                        0}
                      )
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {category.description}
                  </div>
                </div>
              </label>
            )
          })}
        </div>
        <p className="text-xs text-slate-400 mt-3">
          Bot will only trade coins in selected categories.
          Unselected categories are filtered out before
          trading.
        </p>
      </div>

      {/* Max Synthetic Candles % */}
      <div className="mt-4 pt-4 border-t border-slate-600">
        <label className="block text-sm font-medium text-slate-300 mb-2">
          Max Synthetic Candles %
          <span className="text-xs text-slate-400 font-normal ml-2">
            (Skip pairs with too many gap-filled candles)
          </span>
        </label>
        <input
          type="number"
          step="1"
          min="0"
          max="100"
          value={
            formData.strategy_config?.max_synthetic_pct ??
            ''
          }
          onChange={(e) => {
            const val = e.target.value
            setFormData({
              ...formData,
              strategy_config: {
                ...formData.strategy_config,
                max_synthetic_pct:
                  val === ''
                    ? undefined
                    : parseFloat(val),
              },
            })
          }}
          className="w-full sm:w-48 rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
          placeholder="Off"
        />
        <p className="text-xs text-slate-400 mt-1.5">
          Pairs with synthetic candle % above this
          threshold are skipped during analysis. Leave
          empty to disable.
        </p>
      </div>
    </>
  )
}
