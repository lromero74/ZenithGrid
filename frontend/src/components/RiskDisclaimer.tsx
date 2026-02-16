import { useState } from 'react'
import { AlertTriangle, Shield, TrendingDown, DollarSign } from 'lucide-react'

interface RiskDisclaimerProps {
  onAccept: () => void
  onDecline: () => void
  isLoading?: boolean
}

export function RiskDisclaimer({ onAccept, onDecline, isLoading }: RiskDisclaimerProps) {
  const [hasScrolledToBottom, setHasScrolledToBottom] = useState(false)
  const [hasCheckedBox, setHasCheckedBox] = useState(false)

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const element = e.currentTarget
    const isAtBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + 50
    if (isAtBottom) {
      setHasScrolledToBottom(true)
    }
  }

  const canAccept = hasScrolledToBottom && hasCheckedBox

  return (
    <div className="fixed inset-0 bg-slate-900 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-2xl bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-yellow-500/20 rounded-lg">
              <AlertTriangle className="w-6 h-6 text-yellow-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Risk Disclosure & Terms of Use</h2>
              <p className="text-sm text-slate-400">Please read carefully before proceeding</p>
            </div>
          </div>
        </div>

        {/* Scrollable Content */}
        <div
          className="flex-1 overflow-y-auto p-6 space-y-6"
          onScroll={handleScroll}
        >
          {/* Investment Risk Warning */}
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <TrendingDown className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-red-300 mb-2">High Risk Investment Warning</h3>
                <p className="text-sm text-slate-300 leading-relaxed">
                  Cryptocurrency trading involves substantial risk of loss and is not suitable for every investor.
                  The valuation of cryptocurrencies may fluctuate, and you may lose some or all of your investment.
                  <strong className="text-red-300"> You should only invest money that you can afford to lose entirely.</strong>
                </p>
              </div>
            </div>
          </div>

          {/* Automated Trading Risks */}
          <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-yellow-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-yellow-300 mb-2">Automated Trading Risks</h3>
                <p className="text-sm text-slate-300 leading-relaxed">
                  This platform uses automated trading strategies. While automation can help execute trades consistently,
                  it also carries additional risks including but not limited to:
                </p>
                <ul className="mt-2 space-y-1 text-sm text-slate-300 list-disc list-inside">
                  <li>Software bugs or technical failures</li>
                  <li>Exchange API issues or outages</li>
                  <li>Strategy performance may differ from backtests</li>
                  <li>Market conditions can change rapidly</li>
                  <li>Slippage and execution delays</li>
                </ul>
              </div>
            </div>
          </div>

          {/* No Financial Advice */}
          <div className="bg-blue-900/30 border border-blue-700 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <DollarSign className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-blue-300 mb-2">Not Financial Advice</h3>
                <p className="text-sm text-slate-300 leading-relaxed">
                  Nothing on this platform constitutes financial, investment, tax, or legal advice.
                  You are solely responsible for your trading decisions. We strongly recommend consulting
                  with qualified professionals before making any investment decisions.
                </p>
              </div>
            </div>
          </div>

          {/* Terms of Use */}
          <div className="space-y-3">
            <h3 className="font-semibold text-white">Terms of Use</h3>
            <div className="text-sm text-slate-300 space-y-3 leading-relaxed">
              <p>
                By using Zenith Grid, you acknowledge and agree that:
              </p>
              <ol className="list-decimal list-inside space-y-2 pl-2">
                <li>You are at least 18 years of age or the age of majority in your jurisdiction.</li>
                <li>You understand the risks involved in cryptocurrency trading and automated trading systems.</li>
                <li>You are solely responsible for any losses incurred while using this platform.</li>
                <li>Past performance is not indicative of future results.</li>
                <li>You have read and agree to comply with the GNU Affero General Public License v3 (AGPL v3) under which this software is distributed.</li>
                <li>You understand that this software is provided "AS IS" without warranty of any kind, express or implied, including warranties of merchantability, fitness for a particular purpose, and noninfringement.</li>
              </ol>
              <p className="text-red-300 font-semibold mt-4">
                RELEASE OF LIABILITY
              </p>
              <p>
                You hereby release, waive, and forever discharge Romero Tech Solutions, its owners, members, officers,
                employees, agents, and affiliates from any and all liability, claims, demands, actions, or causes of action
                arising out of or related to any loss, damage, or injury sustained as a result of using this software,
                including but not limited to financial losses from trading activities. In no event shall the company be liable
                for any direct, indirect, incidental, special, consequential, or punitive damages.
              </p>
            </div>
          </div>

          {/* Scroll indicator */}
          {!hasScrolledToBottom && (
            <div className="text-center text-sm text-slate-400 animate-pulse">
              Scroll down to read all terms...
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 flex-shrink-0 space-y-4">
          {/* Checkbox */}
          <label className="flex items-start space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={hasCheckedBox}
              onChange={(e) => setHasCheckedBox(e.target.checked)}
              disabled={!hasScrolledToBottom}
              className="mt-1 w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800 disabled:opacity-50"
            />
            <span className={`text-sm ${hasScrolledToBottom ? 'text-slate-200' : 'text-slate-500'}`}>
              I have read and understand the risks involved. I accept full responsibility for my trading decisions
              and agree to the terms of use.
            </span>
          </label>

          {/* Buttons */}
          <div className="flex justify-end space-x-3">
            <button
              onClick={onDecline}
              disabled={isLoading}
              className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
            >
              Decline & Log Out
            </button>
            <button
              onClick={onAccept}
              disabled={!canAccept || isLoading}
              className={`px-6 py-2 font-medium rounded-lg transition-colors ${
                canAccept && !isLoading
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              }`}
            >
              {isLoading ? 'Processing...' : 'I Accept'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
