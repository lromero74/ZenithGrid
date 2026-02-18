/**
 * Toast notification component for order fill alerts
 * Styled to match the dark trading theme
 */

import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, DollarSign, ArrowDownCircle, X, CheckCircle, ArrowUpCircle } from 'lucide-react'

export type ToastType = 'base_order' | 'dca_order' | 'sell_order' | 'partial_fill' | 'info' | 'error' | 'success' | 'update'

export interface ToastData {
  id: string
  type: ToastType
  title: string
  message: string
  productId?: string
  amount?: string
  price?: string
  profit?: string
  timestamp: number
  persistent?: boolean
  actionLabel?: string
  onAction?: () => void
}

interface ToastProps {
  toast: ToastData
  onDismiss: (id: string) => void
}

const TOAST_DURATION = 8000 // 8 seconds

export function Toast({ toast, onDismiss }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    if (toast.persistent) return // Persistent toasts don't auto-dismiss

    const timer = setTimeout(() => {
      setIsExiting(true)
      setTimeout(() => onDismiss(toast.id), 300) // Wait for exit animation
    }, TOAST_DURATION)

    return () => clearTimeout(timer)
  }, [toast.id, toast.persistent, onDismiss])

  const handleDismiss = () => {
    setIsExiting(true)
    setTimeout(() => onDismiss(toast.id), 300)
  }

  // Get icon and colors based on toast type
  const getToastStyles = () => {
    switch (toast.type) {
      case 'base_order':
        return {
          icon: <TrendingUp className="w-6 h-6" />,
          bgColor: 'bg-blue-900/90',
          borderColor: 'border-blue-500',
          iconColor: 'text-blue-400',
          titleColor: 'text-blue-300',
        }
      case 'dca_order':
        return {
          icon: <ArrowDownCircle className="w-6 h-6" />,
          bgColor: 'bg-purple-900/90',
          borderColor: 'border-purple-500',
          iconColor: 'text-purple-400',
          titleColor: 'text-purple-300',
        }
      case 'sell_order':
        return {
          icon: <DollarSign className="w-6 h-6" />,
          bgColor: 'bg-green-900/90',
          borderColor: 'border-green-500',
          iconColor: 'text-green-400',
          titleColor: 'text-green-300',
        }
      case 'partial_fill':
        return {
          icon: <TrendingDown className="w-6 h-6" />,
          bgColor: 'bg-yellow-900/90',
          borderColor: 'border-yellow-500',
          iconColor: 'text-yellow-400',
          titleColor: 'text-yellow-300',
        }
      case 'error':
        return {
          icon: <X className="w-6 h-6" />,
          bgColor: 'bg-red-900/90',
          borderColor: 'border-red-500',
          iconColor: 'text-red-400',
          titleColor: 'text-red-300',
        }
      case 'success':
        return {
          icon: <CheckCircle className="w-6 h-6" />,
          bgColor: 'bg-emerald-900/90',
          borderColor: 'border-emerald-500',
          iconColor: 'text-emerald-400',
          titleColor: 'text-emerald-300',
        }
      case 'update':
        return {
          icon: <ArrowUpCircle className="w-6 h-6" />,
          bgColor: 'bg-amber-900/90',
          borderColor: 'border-amber-500',
          iconColor: 'text-amber-400',
          titleColor: 'text-amber-300',
        }
      default:
        return {
          icon: <TrendingUp className="w-6 h-6" />,
          bgColor: 'bg-slate-800/90',
          borderColor: 'border-slate-500',
          iconColor: 'text-slate-400',
          titleColor: 'text-slate-300',
        }
    }
  }

  const styles = getToastStyles()

  return (
    <div
      className={`
        ${styles.bgColor} ${styles.borderColor}
        border-l-4 rounded-r-lg shadow-lg backdrop-blur-sm
        transform transition-all duration-300 ease-out
        ${isExiting ? 'translate-x-full opacity-0' : 'translate-x-0 opacity-100'}
        max-w-sm w-full pointer-events-auto
      `}
    >
      <div className="p-4">
        <div className="flex items-start">
          {/* Icon */}
          <div className={`flex-shrink-0 ${styles.iconColor}`}>
            {styles.icon}
          </div>

          {/* Content */}
          <div className="ml-3 flex-1">
            <div className="flex items-center justify-between">
              <p className={`text-sm font-semibold ${styles.titleColor}`}>
                {toast.title}
              </p>
              <button
                onClick={handleDismiss}
                className="ml-4 text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="mt-1 text-sm text-slate-300">
              {toast.message}
            </p>

            {/* Action button */}
            {toast.actionLabel && toast.onAction && (
              <button
                onClick={toast.onAction}
                className={`mt-2 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  toast.type === 'update'
                    ? 'bg-amber-600 hover:bg-amber-500 text-white'
                    : 'bg-slate-600 hover:bg-slate-500 text-white'
                }`}
              >
                {toast.actionLabel}
              </button>
            )}

            {/* Order details */}
            {(toast.productId || toast.amount || toast.price) && (
              <div className="mt-2 text-xs text-slate-400 space-y-0.5">
                {toast.productId && (
                  <p>
                    <span className="text-slate-500">Pair:</span>{' '}
                    <span className="font-mono text-slate-300">{toast.productId}</span>
                  </p>
                )}
                {toast.amount && (
                  <p>
                    <span className="text-slate-500">Amount:</span>{' '}
                    <span className="font-mono text-slate-300">{toast.amount}</span>
                  </p>
                )}
                {toast.price && (
                  <p>
                    <span className="text-slate-500">Price:</span>{' '}
                    <span className="font-mono text-slate-300">{toast.price}</span>
                  </p>
                )}
                {toast.profit && (
                  <p>
                    <span className="text-slate-500">Profit:</span>{' '}
                    <span className={`font-mono ${
                      toast.profit.startsWith('+') ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {toast.profit}
                    </span>
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Progress bar (hidden for persistent toasts) */}
      {!toast.persistent && (
        <>
          <div className="h-1 bg-slate-700/50 overflow-hidden">
            <div
              className={`h-full ${styles.borderColor.replace('border', 'bg')}`}
              style={{
                animation: `shrink ${TOAST_DURATION}ms linear forwards`,
              }}
            />
          </div>

          <style>{`
            @keyframes shrink {
              from { width: 100%; }
              to { width: 0%; }
            }
          `}</style>
        </>
      )}
    </div>
  )
}

interface ToastContainerProps {
  toasts: ToastData[]
  onDismiss: (id: string) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-3 pointer-events-none">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
