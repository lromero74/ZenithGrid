import type { BotFormData } from '../../../components/bots'

interface BudgetSectionProps {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
}

export function BudgetSection({
  formData,
  setFormData,
}: BudgetSectionProps) {
  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">6.</span> Budget
        & Risk Management
      </h3>

      {/* Budget Allocation */}
      <div className="bg-orange-900/20 border border-orange-700/50 rounded-lg p-4 mb-4">
        <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          Budget Allocation{' '}
          <span className="text-xs font-normal text-slate-400">
            (Optional)
          </span>
        </h4>
        <p className="text-xs text-slate-300 mb-3">
          Set bot budget as a percentage of aggregate
          portfolio value. Leave at 0 to use total
          portfolio balance.
        </p>

        {/* Budget Percentage */}
        <div className="mb-4">
          <label className="block text-xs font-medium text-emerald-300 mb-1.5">
            Budget Percentage{' '}
            <span className="text-slate-400">
              (% of aggregate portfolio)
            </span>
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={
                formData.budget_percentage ===
                  undefined ||
                formData.budget_percentage === null
                  ? ''
                  : formData.budget_percentage
              }
              onChange={(e) => {
                const val = e.target.value
                setFormData({
                  ...formData,
                  budget_percentage:
                    val === ''
                      ? undefined
                      : parseFloat(val),
                })
              }}
              onBlur={(e) => {
                if (
                  e.target.value === '' ||
                  isNaN(parseFloat(e.target.value))
                ) {
                  setFormData({
                    ...formData,
                    budget_percentage: 0,
                  })
                }
              }}
              className="flex-1 rounded border border-emerald-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
              placeholder="0.0"
            />
            <span className="text-emerald-400 font-medium">
              %
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Recommended: 33% for 3 bots, 50% for 2 bots,
            100% for 1 bot
          </p>
        </div>

        {/* Legacy Reserved Balances */}
        <details className="text-xs text-slate-400">
          <summary className="cursor-pointer hover:text-slate-300 mb-2">
            Legacy: Fixed Reserved Balances (deprecated)
          </summary>
          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Reserved BTC
              </label>
              <input
                type="number"
                step="0.00000001"
                min="0"
                value={
                  formData.reserved_btc_balance ===
                    undefined ||
                  formData.reserved_btc_balance === null
                    ? ''
                    : formData.reserved_btc_balance
                }
                onChange={(e) => {
                  const val = e.target.value
                  setFormData({
                    ...formData,
                    reserved_btc_balance:
                      val === ''
                        ? undefined
                        : parseFloat(val),
                  })
                }}
                onBlur={(e) => {
                  if (
                    e.target.value === '' ||
                    isNaN(parseFloat(e.target.value))
                  ) {
                    setFormData({
                      ...formData,
                      reserved_btc_balance: 0,
                    })
                  }
                }}
                className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                placeholder="0.0"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Reserved USD
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={
                  formData.reserved_usd_balance ===
                    undefined ||
                  formData.reserved_usd_balance === null
                    ? ''
                    : formData.reserved_usd_balance
                }
                onChange={(e) => {
                  const val = e.target.value
                  setFormData({
                    ...formData,
                    reserved_usd_balance:
                      val === ''
                        ? undefined
                        : parseFloat(val),
                  })
                }}
                onBlur={(e) => {
                  if (
                    e.target.value === '' ||
                    isNaN(parseFloat(e.target.value))
                  ) {
                    setFormData({
                      ...formData,
                      reserved_usd_balance: 0,
                    })
                  }
                }}
                className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                placeholder="0.00"
              />
            </div>
          </div>
        </details>
      </div>

      {/* Budget Splitting Toggle - multi-pair only */}
      {formData.product_ids.length > 1 && (
        <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-4">
          <label className="flex items-start space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={
                formData.split_budget_across_pairs
              }
              onChange={(e) =>
                setFormData({
                  ...formData,
                  split_budget_across_pairs:
                    e.target.checked,
                })
              }
              className="mt-1 rounded border-slate-500"
            />
            <div className="flex-1">
              <div className="font-medium text-white mb-1">
                Split Budget Across Pairs
              </div>
              <div className="text-sm text-slate-300">
                {formData.split_budget_across_pairs ? (
                  <>
                    <span className="text-green-400">
                      Enabled:
                    </span>{' '}
                    Budget percentages will be divided by{' '}
                    {formData.strategy_config
                      ?.max_concurrent_deals || 1}{' '}
                    max concurrent deals.
                    <br />
                    <span className="text-xs text-slate-400">
                      Example: 30% max usage /{' '}
                      {formData.strategy_config
                        ?.max_concurrent_deals || 1}{' '}
                      ={' '}
                      {(
                        30 /
                        (formData.strategy_config
                          ?.max_concurrent_deals || 1)
                      ).toFixed(1)}
                      % per deal (safer)
                    </span>
                  </>
                ) : (
                  <>
                    <span className="text-yellow-400">
                      Disabled:
                    </span>{' '}
                    Each deal gets full budget allocation
                    independently.
                    <br />
                    <span className="text-xs text-slate-400">
                      Example: 30% max usage x{' '}
                      {formData.strategy_config
                        ?.max_concurrent_deals || 1}{' '}
                      deals = up to{' '}
                      {30 *
                        (formData.strategy_config
                          ?.max_concurrent_deals || 1)}
                      % total (deal-based allocation)
                    </span>
                  </>
                )}
              </div>
            </div>
          </label>
        </div>
      )}
    </div>
  )
}
