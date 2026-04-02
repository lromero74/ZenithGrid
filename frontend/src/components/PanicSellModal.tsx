import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { positionsApi } from '../services/api'

type Step = 'configure' | 'confirm' | 'mfa' | 'progress' | 'done'
type Action = 'cancel' | 'sell'
type TargetCurrency = 'USD' | 'USDC' | 'USDT' | 'BTC' | 'ETH'
type MfaMethod = 'totp' | 'email' | 'none'

interface PanicSellModalProps {
  isOpen: boolean
  onClose: () => void
  accountId: number
}

const CURRENCIES: TargetCurrency[] = ['USD', 'USDC', 'USDT', 'BTC', 'ETH']

const PHASES = ['stopping_bots', 'closing_positions', 'stopping_rebalancers', 'converting', 'completed']
const PHASE_LABELS: Record<string, string> = {
  stopping_bots: 'Stopping bots',
  closing_positions: 'Closing positions',
  stopping_rebalancers: 'Disabling features',
  converting: 'Converting portfolio',
  completed: 'Complete',
}

export function PanicSellModal({ isOpen, onClose, accountId }: PanicSellModalProps) {
  const [step, setStep] = useState<Step>('configure')
  const [action, setAction] = useState<Action>('cancel')
  const [targetCurrency, setTargetCurrency] = useState<TargetCurrency>('USD')
  const [stopBots, setStopBots] = useState(true)
  const [stopPortfolioRebalancer, setStopPortfolioRebalancer] = useState(true)
  const [stopBotRebalancer, setStopBotRebalancer] = useState(true)
  const [stopAutoBuy, setStopAutoBuy] = useState(true)
  const [zeroMinBalances, setZeroMinBalances] = useState(true)
  const [confirmText, setConfirmText] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [mfaMethod, setMfaMethod] = useState<MfaMethod | null>(null)
  const [mfaMaskedEmail, setMfaMaskedEmail] = useState<string | null>(null)
  const [mfaSending, setMfaSending] = useState(false)
  const [mfaSent, setMfaSent] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const mfaInputRef = useRef<HTMLInputElement>(null)

  // Poll progress while running
  const { data: progress } = useQuery({
    queryKey: ['panic-sell-status', taskId],
    queryFn: () => positionsApi.panicSellStatus(taskId!),
    enabled: !!taskId && step === 'progress',
    refetchInterval: 1500,
    refetchIntervalInBackground: false,
  })

  // Advance to done when complete
  useEffect(() => {
    if (progress?.status === 'completed' || progress?.status === 'failed') {
      setStep('done')
    }
  }, [progress?.status])

  // Focus inputs when step changes
  useEffect(() => {
    if (step === 'confirm') setTimeout(() => confirmInputRef.current?.focus(), 100)
    if (step === 'mfa') setTimeout(() => mfaInputRef.current?.focus(), 100)
  }, [step])

  if (!isOpen) return null

  const handleGoToMfa = async () => {
    setMfaSending(true)
    setSubmitError(null)
    try {
      const result = await positionsApi.panicSellSendMfa()
      setMfaMethod(result.method)
      setMfaMaskedEmail(result.masked_email || null)
      if (result.method === 'email') setMfaSent(true)
      if (result.method === 'none') {
        // No MFA — submit directly
        await _doSubmit(undefined)
        return
      }
      setStep('mfa')
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setSubmitError(e.response?.data?.detail || e.message || 'Unknown error')
    } finally {
      setMfaSending(false)
    }
  }

  const handleResendMfa = async () => {
    setMfaSending(true)
    try {
      await positionsApi.panicSellSendMfa()
      setMfaSent(true)
      setMfaCode('')
    } finally {
      setMfaSending(false)
    }
  }

  const _doSubmit = async (code: string | undefined) => {
    setIsSubmitting(true)
    setSubmitError(null)
    try {
      const result = await positionsApi.panicSell({
        account_id: accountId,
        action,
        target_currency: action === 'sell' ? targetCurrency : undefined,
        stop_bots: stopBots,
        stop_portfolio_rebalancer: stopPortfolioRebalancer,
        stop_bot_rebalancer: stopBotRebalancer,
        stop_auto_buy: stopAutoBuy,
        zero_min_balances: zeroMinBalances,
        mfa_code: code,
        confirm: true,
      })
      setTaskId(result.task_id)
      setStep('progress')
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setSubmitError(e.response?.data?.detail || e.message || 'Unknown error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleMfaSubmit = () => _doSubmit(mfaCode)

  const handleClose = () => {
    if (step === 'progress') return // Block close during progress
    setStep('configure')
    setConfirmText('')
    setMfaCode('')
    setMfaMethod(null)
    setMfaMaskedEmail(null)
    setMfaSent(false)
    setTaskId(null)
    setSubmitError(null)
    onClose()
  }

  const isPhaseComplete = (phase: string) => {
    if (!progress) return false
    const currentIdx = PHASES.indexOf(progress.phase)
    const phaseIdx = PHASES.indexOf(phase)
    return phaseIdx < currentIdx || progress.status === 'completed'
  }

  const isPhaseActive = (phase: string) => {
    return progress?.phase === phase && progress?.status === 'running'
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" data-testid="panic-sell-modal">
      <div className="bg-slate-800 border border-slate-700 rounded-xl w-full max-w-md shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🚨</span>
            <h2 className="text-lg font-bold text-white">Emergency Liquidation</h2>
          </div>
          {step !== 'progress' && (
            <button onClick={handleClose} className="text-slate-400 hover:text-white transition-colors text-xl leading-none">
              ✕
            </button>
          )}
        </div>

        <div className="p-6">

          {/* ── Step 1: Configure ─────────────────────────────────────────── */}
          {step === 'configure' && (
            <div className="space-y-5">
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-300">
                ⚠️ This will immediately act on ALL open positions across all bots for this account.
              </div>

              {/* Action choice */}
              <div>
                <p className="text-sm font-medium text-slate-300 mb-2">Action</p>
                <div className="space-y-2">
                  {(['cancel', 'sell'] as Action[]).map((a) => (
                    <label key={a} className="flex items-start gap-3 cursor-pointer group">
                      <input
                        type="radio"
                        name="action"
                        value={a}
                        checked={action === a}
                        onChange={() => setAction(a)}
                        className="mt-0.5 accent-red-500"
                      />
                      <span className="text-sm">
                        <span className="text-white font-medium">
                          {a === 'cancel' ? 'Cancel All Deals' : 'Sell All at Market'}
                        </span>
                        <span className="block text-slate-400 text-xs mt-0.5">
                          {a === 'cancel'
                            ? 'Marks positions as cancelled — no exchange orders placed'
                            : 'Executes market sell orders on the exchange immediately'}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Target currency (sell only) */}
              {action === 'sell' && (
                <div>
                  <p className="text-sm font-medium text-slate-300 mb-2">Convert to</p>
                  <div className="flex flex-wrap gap-2">
                    {CURRENCIES.map((c) => (
                      <button
                        key={c}
                        onClick={() => setTargetCurrency(c)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                          targetCurrency === c
                            ? 'bg-red-600/30 border-red-500 text-red-300'
                            : 'bg-slate-700 border-slate-600 text-slate-300 hover:border-slate-500'
                        }`}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-slate-500 mt-2">
                    Positions close to their quote currency first. Free balances are then converted
                    to {targetCurrency}. Assets without a direct pair go through an intermediate automatically.
                  </p>
                </div>
              )}

              {/* Options */}
              <div>
                <p className="text-sm font-medium text-slate-300 mb-2">Also</p>
                <div className="space-y-2">
                  {[
                    { key: 'stopBots', label: 'Stop all active bots', desc: 'Prevents new deals from opening', value: stopBots, set: setStopBots },
                    { key: 'stopPortfolioRebalancer', label: 'Disable portfolio rebalancer', desc: 'Stops automatic portfolio rebalancing', value: stopPortfolioRebalancer, set: setStopPortfolioRebalancer },
                    { key: 'stopBotRebalancer', label: 'Disable bot rebalancer groups', desc: 'Stops per-bot rebalancer groups', value: stopBotRebalancer, set: setStopBotRebalancer },
                    { key: 'stopAutoBuy', label: 'Disable auto-buy BTC', desc: 'Stops automatic stablecoin → BTC conversion', value: stopAutoBuy, set: setStopAutoBuy },
                    { key: 'zeroMinBalances', label: 'Zero out minimum balance reserves', desc: 'Removes all balance floors so conversion can proceed fully', value: zeroMinBalances, set: setZeroMinBalances },
                  ].map(({ key, label, desc, value, set }) => (
                    <label key={key} className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={(e) => set(e.target.checked)}
                        className="mt-0.5 accent-red-500"
                      />
                      <span className="text-sm">
                        <span className="text-white">{label}</span>
                        <span className="block text-slate-400 text-xs mt-0.5">{desc}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <button
                onClick={() => setStep('confirm')}
                className="w-full bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-lg font-semibold transition-colors"
              >
                Next →
              </button>
            </div>
          )}

          {/* ── Step 2: Confirm ───────────────────────────────────────────── */}
          {step === 'confirm' && (
            <div className="space-y-5">
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm space-y-1.5">
                <p className="text-red-300 font-semibold mb-2">This will:</p>
                <p className="text-slate-300">
                  • <strong>{action === 'cancel' ? 'Cancel' : 'Sell'}</strong> all open positions
                  {action === 'sell' && ` and convert proceeds to ${targetCurrency}`}
                </p>
                {stopBots && <p className="text-slate-300">• Stop all active bots</p>}
                {stopPortfolioRebalancer && <p className="text-slate-300">• Disable portfolio rebalancer</p>}
                {stopBotRebalancer && <p className="text-slate-300">• Disable bot rebalancer groups</p>}
                {stopAutoBuy && <p className="text-slate-300">• Disable auto-buy BTC</p>}
                {zeroMinBalances && <p className="text-slate-300">• Zero out minimum balance reserves</p>}
              </div>

              <div>
                <label className="block text-sm text-slate-300 mb-2">
                  Type <span className="font-mono font-bold text-red-400">CONFIRM</span> to proceed
                </label>
                <input
                  ref={confirmInputRef}
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="CONFIRM"
                  className="w-full bg-slate-700 border border-slate-600 text-white px-3 py-2 rounded-lg text-sm focus:outline-none focus:border-red-500"
                />
              </div>

              {submitError && (
                <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  {submitError}
                </p>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => setStep('configure')}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-slate-300 py-2.5 rounded-lg font-semibold transition-colors"
                >
                  ← Back
                </button>
                <button
                  onClick={handleGoToMfa}
                  disabled={confirmText !== 'CONFIRM' || mfaSending}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-lg font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {mfaSending ? 'Verifying...' : 'Next →'}
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: MFA ───────────────────────────────────────────────── */}
          {step === 'mfa' && (
            <div className="space-y-5">
              <div className="text-center space-y-1">
                <p className="text-2xl">🔐</p>
                <p className="text-white font-semibold">MFA Verification</p>
                {mfaMethod === 'totp' && (
                  <p className="text-sm text-slate-400">Enter the code from your authenticator app</p>
                )}
                {mfaMethod === 'email' && (
                  <p className="text-sm text-slate-400">
                    {mfaSent
                      ? <>A 6-digit code was sent to <span className="text-white">{mfaMaskedEmail}</span></>
                      : 'Sending code...'}
                  </p>
                )}
              </div>

              <div>
                <input
                  ref={mfaInputRef}
                  type="text"
                  inputMode="numeric"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  className="w-full bg-slate-700 border border-slate-600 text-white px-3 py-3 rounded-lg text-center text-xl tracking-widest font-mono focus:outline-none focus:border-red-500"
                  onKeyDown={(e) => { if (e.key === 'Enter' && mfaCode.length === 6) handleMfaSubmit() }}
                />
              </div>

              {mfaMethod === 'email' && (
                <button
                  onClick={handleResendMfa}
                  disabled={mfaSending}
                  className="w-full text-sm text-slate-400 hover:text-slate-300 transition-colors disabled:opacity-50"
                >
                  {mfaSending ? 'Sending...' : 'Resend code'}
                </button>
              )}

              {submitError && (
                <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  {submitError}
                </p>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => { setStep('confirm'); setSubmitError(null) }}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-slate-300 py-2.5 rounded-lg font-semibold transition-colors"
                >
                  ← Back
                </button>
                <button
                  onClick={handleMfaSubmit}
                  disabled={mfaCode.length !== 6 || isSubmitting}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-lg font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? 'Initiating...' : '🚨 Execute'}
                </button>
              </div>
            </div>
          )}

          {/* ── Step 4: Progress ──────────────────────────────────────────── */}
          {step === 'progress' && (
            <div className="space-y-5">
              <p className="text-sm text-slate-400 text-center">
                {progress?.message || 'Initializing...'}
              </p>

              <div className="space-y-3">
                {Object.entries(PHASE_LABELS).filter(([k]) => k !== 'completed').map(([phase, label]) => {
                  const complete = isPhaseComplete(phase)
                  const active = isPhaseActive(phase)
                  return (
                    <div key={phase} className="flex items-center gap-3">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${
                        complete ? 'bg-green-500/20 text-green-400' :
                        active ? 'bg-red-500/20 text-red-400' :
                        'bg-slate-700 text-slate-500'
                      }`}>
                        {complete ? '✓' : active ? '●' : '○'}
                      </div>
                      <span className={`text-sm flex-1 ${complete ? 'text-green-400' : active ? 'text-white' : 'text-slate-500'}`}>
                        {label}
                      </span>
                      {phase === 'closing_positions' && progress && progress.positions_total > 0 && (
                        <div className="flex items-center gap-2">
                          <div className="w-24 bg-slate-700 rounded-full h-1.5">
                            <div
                              className="bg-red-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${progress.progress_pct}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-400">
                            {progress.positions_current}/{progress.positions_total}
                          </span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {progress && progress.errors.length > 0 && (
                <details className="text-xs text-red-400">
                  <summary className="cursor-pointer">{progress.errors.length} error(s)</summary>
                  <ul className="mt-1 space-y-0.5 pl-2">
                    {progress.errors.map((e, i) => <li key={i}>• {e}</li>)}
                  </ul>
                </details>
              )}
            </div>
          )}

          {/* ── Step 5: Done ──────────────────────────────────────────────── */}
          {step === 'done' && progress && (
            <div className="space-y-4">
              {progress.status === 'failed' ? (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-300">
                  <p className="font-semibold mb-1">Panic sell failed</p>
                  <p>{progress.message}</p>
                </div>
              ) : (
                <div className="space-y-2 text-sm">
                  <p className="text-green-400 font-semibold mb-3">✓ Complete</p>
                  {progress.bots_stopped > 0 && (
                    <p className="text-slate-300">✓ {progress.bots_stopped} bot(s) stopped</p>
                  )}
                  <p className="text-slate-300">
                    ✓ {progress.positions_acted} position(s) {action === 'cancel' ? 'cancelled' : 'sold'}
                    {progress.positions_failed > 0 && (
                      <span className="text-red-400"> ({progress.positions_failed} failed)</span>
                    )}
                  </p>
                  {progress.portfolio_rebalancer_stopped && (
                    <p className="text-slate-300">✓ Portfolio rebalancer disabled</p>
                  )}
                  {progress.bot_rebalancer_groups_stopped > 0 && (
                    <p className="text-slate-300">✓ {progress.bot_rebalancer_groups_stopped} bot rebalancer group(s) disabled</p>
                  )}
                  {progress.auto_buy_stopped && (
                    <p className="text-slate-300">✓ Auto-buy BTC disabled</p>
                  )}
                  {progress.min_balances_zeroed && (
                    <p className="text-slate-300">✓ Minimum balance reserves zeroed</p>
                  )}
                  {progress.conversion_task_id && (
                    <p className="text-slate-300">
                      ✓ Portfolio conversion started
                      <span className="text-slate-500 text-xs ml-1">(task {progress.conversion_task_id.slice(0, 8)})</span>
                    </p>
                  )}
                </div>
              )}

              {progress.errors.length > 0 && (
                <details className="text-xs text-red-400">
                  <summary className="cursor-pointer">{progress.errors.length} error(s)</summary>
                  <ul className="mt-1 space-y-0.5 pl-2">
                    {progress.errors.map((e, i) => <li key={i}>• {e}</li>)}
                  </ul>
                </details>
              )}

              <button
                onClick={handleClose}
                className="w-full bg-slate-700 hover:bg-slate-600 text-white py-2.5 rounded-lg font-semibold transition-colors mt-2"
              >
                Close
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
