/**
 * Donation Modal — polite popup with quarterly meter, donation addresses,
 * QR codes for crypto, and self-report form.
 */

import { useState, useEffect, useCallback } from 'react'
import { Heart, X, Copy, Check, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { donationsApi, type DonationGoal } from '../services/api'

const DONATION_DISMISSED_QUARTER_KEY = 'donation_modal_dismissed_quarter'

/** Get current quarter string like "2026-Q1" */
function getCurrentQuarter(): string {
  const now = new Date()
  const q = Math.ceil((now.getMonth() + 1) / 3)
  return `${now.getFullYear()}-Q${q}`
}

const CRYPTO_METHODS = [
  {
    id: 'btc',
    label: 'Bitcoin (BTC)',
    address: '3LehBoma3aeDwdgMYK3hyr2TGfxkJs55MV',
    qrValue: 'bitcoin:3LehBoma3aeDwdgMYK3hyr2TGfxkJs55MV',
  },
  {
    id: 'usdc',
    label: 'USDC (ERC-20)',
    address: '0x8B7Ff39C772c90AB58A3d74dCd17F1425b4001c0',
    qrValue: '0x8B7Ff39C772c90AB58A3d74dCd17F1425b4001c0',
  },
]

const APP_METHODS = [
  { id: 'paypal', label: 'PayPal', handle: '@farolito74', url: 'https://paypal.me/farolito74' },
  { id: 'venmo', label: 'Venmo', handle: '@Louis-Romero-5', url: 'https://venmo.com/Louis-Romero-5' },
  { id: 'cashapp', label: 'CashApp', handle: '$Farolito74', url: 'https://cash.app/$Farolito74' },
]

const PAYMENT_METHODS = [
  { value: 'btc', label: 'Bitcoin' },
  { value: 'usdc', label: 'USDC' },
  { value: 'paypal', label: 'PayPal' },
  { value: 'venmo', label: 'Venmo' },
  { value: 'cashapp', label: 'CashApp' },
]

interface DonationModalProps {
  isOpen: boolean
  onClose: () => void
}

export function DonationModal({ isOpen, onClose }: DonationModalProps) {
  const [goal, setGoal] = useState<DonationGoal | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [showQR, setShowQR] = useState<string | null>(null)
  const [copiedAddr, setCopiedAddr] = useState<string | null>(null)
  const [dontRemind, setDontRemind] = useState(false)

  // Report form
  const [reportAmount, setReportAmount] = useState('')
  const [reportMethod, setReportMethod] = useState('paypal')
  const [reportRef, setReportRef] = useState('')
  const [reportSubmitting, setReportSubmitting] = useState(false)
  const [reportSuccess, setReportSuccess] = useState(false)

  useEffect(() => {
    if (isOpen) {
      donationsApi.getGoal().then(setGoal).catch(() => {})
      setShowReport(false)
      setReportSuccess(false)
    }
  }, [isOpen])

  const handleCopy = useCallback(async (address: string) => {
    try {
      await navigator.clipboard.writeText(address)
      setCopiedAddr(address)
      setTimeout(() => setCopiedAddr(null), 2000)
    } catch {
      // Fallback for older browsers
    }
  }, [])

  const handleDismiss = useCallback(() => {
    if (dontRemind) {
      localStorage.setItem(DONATION_DISMISSED_QUARTER_KEY, getCurrentQuarter())
    }
    onClose()
  }, [dontRemind, onClose])

  const handleSubmitReport = useCallback(async () => {
    const amount = parseFloat(reportAmount)
    if (!amount || amount <= 0) return

    setReportSubmitting(true)
    try {
      await donationsApi.reportDonation({
        amount,
        currency: 'USD',
        payment_method: reportMethod,
        tx_reference: reportRef || undefined,
      })
      setReportSuccess(true)
      // Don't bother them again this quarter — they donated
      localStorage.setItem(DONATION_DISMISSED_QUARTER_KEY, getCurrentQuarter())
      // Refresh goal
      donationsApi.getGoal().then(setGoal).catch(() => {})
    } catch {
      // Error handled silently
    } finally {
      setReportSubmitting(false)
    }
  }, [reportAmount, reportMethod, reportRef])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-2 sm:p-4" onClick={handleDismiss}>
      <div
        className="bg-slate-800 rounded-xl w-full max-w-lg max-h-[95vh] flex flex-col border border-slate-700 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-700 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <Heart className="w-5 h-5 text-rose-400" />
            <h2 className="text-lg font-bold text-white">Help Keep This Free</h2>
          </div>
          <button onClick={handleDismiss} className="text-slate-400 hover:text-white p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          {/* Monthly meter */}
          {goal && (
            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-slate-300">Quarterly Goal</span>
                <span className="text-white font-medium">
                  ${goal.current.toFixed(0)} of ${goal.target.toFixed(0)}
                </span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
                  style={{ width: `${Math.min(goal.percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs mt-1.5">
                <span className="text-slate-500">{goal.donation_count} donation{goal.donation_count !== 1 ? 's' : ''} this quarter</span>
                <span className="text-emerald-400 font-medium">{goal.percentage}%</span>
              </div>
            </div>
          )}

          {/* Message */}
          <p className="text-sm text-slate-300 leading-relaxed">
            This platform is free to use &mdash; no subscriptions, no ads, no hidden fees.
            But servers, APIs, and development take time and money.
          </p>
          <p className="text-sm text-slate-400 leading-relaxed">
            If you&apos;re getting value from this tool, consider making a donation of any amount.
            Every contribution helps keep the lights on and new features coming.
          </p>

          {/* Crypto addresses */}
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Cryptocurrency</h3>
            <div className="space-y-2">
              {CRYPTO_METHODS.map(method => (
                <div key={method.id} className="bg-slate-900/50 rounded-lg p-3 border border-slate-700/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-slate-200">{method.label}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleCopy(method.address)}
                        className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                        title="Copy address"
                      >
                        {copiedAddr === method.address ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                      <button
                        onClick={() => setShowQR(showQR === method.id ? null : method.id)}
                        className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                        title="Show QR code"
                      >
                        {showQR === method.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 font-mono break-all">{method.address}</p>
                  {showQR === method.id && (
                    <div className="mt-3 flex justify-center bg-white rounded-lg p-3 mx-auto w-fit">
                      <QRCodeSVG value={method.qrValue} size={140} level="M" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Payment apps */}
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Payment Apps</h3>
            <div className="grid grid-cols-3 gap-2">
              {APP_METHODS.map(method => (
                <a
                  key={method.id}
                  href={method.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col items-center gap-1 p-3 bg-slate-900/50 rounded-lg border border-slate-700/50 hover:border-slate-600 hover:bg-slate-700/30 transition-colors"
                >
                  <span className="text-sm font-medium text-slate-200">{method.label}</span>
                  <span className="text-xs text-slate-500">{method.handle}</span>
                  <ExternalLink className="w-3 h-3 text-slate-500 mt-0.5" />
                </a>
              ))}
            </div>
          </div>

          {/* Self-report */}
          {!reportSuccess ? (
            <div>
              <button
                onClick={() => setShowReport(!showReport)}
                className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
              >
                {showReport ? 'Cancel' : 'I already donated'}
              </button>
              {showReport && (
                <div className="mt-3 space-y-3 bg-slate-900/50 rounded-lg p-4 border border-slate-700/50">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Amount (USD)</label>
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={reportAmount}
                        onChange={e => setReportAmount(e.target.value)}
                        className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-sm text-white"
                        placeholder="25.00"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Method</label>
                      <select
                        value={reportMethod}
                        onChange={e => setReportMethod(e.target.value)}
                        className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-sm text-white"
                      >
                        {PAYMENT_METHODS.map(m => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Transaction Ref (optional)</label>
                    <input
                      type="text"
                      value={reportRef}
                      onChange={e => setReportRef(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-sm text-white"
                      placeholder="PayPal transaction ID, BTC tx hash, etc."
                    />
                  </div>
                  <button
                    onClick={handleSubmitReport}
                    disabled={reportSubmitting || !reportAmount || parseFloat(reportAmount) <= 0}
                    className="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
                  >
                    {reportSubmitting ? 'Submitting...' : 'Submit Report'}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-emerald-400 text-sm bg-emerald-900/20 rounded-lg p-3 border border-emerald-700/30">
              <Check className="w-4 h-4 shrink-0" />
              <span>Thank you! Your donation will be confirmed by an admin.</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 shrink-0 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
            <input
              type="checkbox"
              checked={dontRemind}
              onChange={e => setDontRemind(e.target.checked)}
              className="rounded border-slate-600"
            />
            Don&apos;t remind me this quarter
          </label>
          <button
            onClick={handleDismiss}
            className="px-4 py-2 text-sm text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Maybe Later
          </button>
        </div>
      </div>
    </div>
  )
}

/** Check if the donation modal should auto-show this quarter. */
export function shouldShowDonationModal(): boolean {
  const currentQuarter = getCurrentQuarter()
  const dismissedQuarter = localStorage.getItem(DONATION_DISMISSED_QUARTER_KEY)
  return dismissedQuarter !== currentQuarter
}
