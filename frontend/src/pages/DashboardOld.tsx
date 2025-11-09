import { useQuery, useMutation } from '@tanstack/react-query'
import { dashboardApi, monitorApi } from '../services/api'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Activity, Pause, Play, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import TradingChart from '../components/TradingChart'

export default function Dashboard() {
  const [isTogglingMonitor, setIsTogglingMonitor] = useState(false)

  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: dashboardApi.getStats,
    refetchInterval: 5000, // Refetch every 5 seconds
  })

  const cancelPositionMutation = useMutation({
    mutationFn: (positionId: number) =>
      axios.post(`/api/positions/${positionId}/cancel`),
    onSuccess: () => {
      refetchStats()
      alert('Position cancelled successfully')
    },
    onError: (error: any) => {
      alert(`Error cancelling position: ${error.response?.data?.detail || error.message}`)
    },
  })

  const forceClosePositionMutation = useMutation({
    mutationFn: (positionId: number) =>
      axios.post(`/api/positions/${positionId}/force-close`),
    onSuccess: (response) => {
      refetchStats()
      const data = response.data
      alert(
        `Position closed!\nProfit: ${data.profit_btc?.toFixed(8)} BTC (${data.profit_percentage?.toFixed(2)}%)`
      )
    },
    onError: (error: any) => {
      alert(`Error closing position: ${error.response?.data?.detail || error.message}`)
    },
  })

  const handleToggleMonitor = async () => {
    if (!stats) return

    setIsTogglingMonitor(true)
    try {
      if (stats.monitor_running) {
        await monitorApi.stop()
      } else {
        await monitorApi.start()
      }
      await refetchStats()
    } catch (error) {
      console.error('Error toggling monitor:', error)
    } finally {
      setIsTogglingMonitor(false)
    }
  }

  const handleCancelPosition = (positionId: number) => {
    if (confirm('Are you sure you want to cancel this position? ETH will remain in your account.')) {
      cancelPositionMutation.mutate(positionId)
    }
  }

  const handleForceClosePosition = (positionId: number) => {
    if (confirm('Are you sure you want to close this position at market price?')) {
      forceClosePositionMutation.mutate(positionId)
    }
  }

  const formatPrice = (price: number) => price.toFixed(8)
  const formatBTC = (btc: number) => `${btc.toFixed(8)} BTC`

  return (
    <div className="space-y-6">
      {/* Control Bar */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Dashboard</h2>
        <button
          onClick={handleToggleMonitor}
          disabled={isTogglingMonitor}
          className={`${
            stats?.monitor_running ? 'btn-danger' : 'btn-success'
          } flex items-center space-x-2`}
        >
          {stats?.monitor_running ? (
            <>
              <Pause className="w-4 h-4" />
              <span>Stop Bot</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              <span>Start Bot</span>
            </>
          )}
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Current Price</p>
              <p className="text-2xl font-bold mt-1">{formatPrice(stats?.current_price || 0)}</p>
              <p className="text-xs text-slate-500 mt-1">ETH/BTC</p>
            </div>
            <Activity className="w-10 h-10 text-blue-500 opacity-50" />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Total Profit</p>
              <p className={`text-2xl font-bold mt-1 ${
                (stats?.total_profit_btc || 0) >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {formatBTC(stats?.total_profit_btc || 0)}
              </p>
              <p className="text-xs text-slate-500 mt-1">All time</p>
            </div>
            <DollarSign className={`w-10 h-10 opacity-50 ${
              (stats?.total_profit_btc || 0) >= 0 ? 'text-green-500' : 'text-red-500'
            }`} />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Win Rate</p>
              <p className="text-2xl font-bold mt-1">{stats?.win_rate.toFixed(1)}%</p>
              <p className="text-xs text-slate-500 mt-1">{stats?.total_positions} positions</p>
            </div>
            <TrendingUp className="w-10 h-10 text-purple-500 opacity-50" />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">BTC Balance</p>
              <p className="text-2xl font-bold mt-1">{(stats?.btc_balance || 0).toFixed(6)}</p>
              <p className="text-xs text-slate-500 mt-1">ETH: {(stats?.eth_balance || 0).toFixed(6)}</p>
            </div>
            <DollarSign className="w-10 h-10 text-yellow-500 opacity-50" />
          </div>
        </div>
      </div>

      {/* Current Position */}
      {stats?.current_position && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold flex items-center">
              <Activity className="w-5 h-5 mr-2 text-green-500" />
              Active Position
            </h3>
            <div className="flex space-x-2">
              <button
                onClick={() => handleCancelPosition(stats.current_position!.id)}
                disabled={cancelPositionMutation.isPending}
                className="btn-secondary flex items-center space-x-2"
              >
                <X className="w-4 h-4" />
                <span>Cancel</span>
              </button>
              <button
                onClick={() => handleForceClosePosition(stats.current_position!.id)}
                disabled={forceClosePositionMutation.isPending}
                className="btn-danger flex items-center space-x-2"
              >
                <XCircle className="w-4 h-4" />
                <span>Force Close</span>
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="text-slate-400 text-sm">Total BTC Spent</p>
              <p className="text-lg font-semibold">{formatBTC(stats.current_position.total_btc_spent)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-sm">ETH Acquired</p>
              <p className="text-lg font-semibold">{stats.current_position.total_eth_acquired.toFixed(6)} ETH</p>
            </div>
            <div>
              <p className="text-slate-400 text-sm">Avg Buy Price</p>
              <p className="text-lg font-semibold">{formatPrice(stats.current_position.average_buy_price)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-sm">Trades</p>
              <p className="text-lg font-semibold">{stats.current_position.trade_count}</p>
            </div>
            <div>
              <p className="text-slate-400 text-sm">Max BTC Allowed</p>
              <p className="text-lg font-semibold">{formatBTC(stats.current_position.max_btc_allowed)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-sm">Usage</p>
              <p className="text-lg font-semibold">
                {((stats.current_position.total_btc_spent / stats.current_position.max_btc_allowed) * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TradingView-Style Chart */}
      <TradingChart productId="ETH-BTC" />
    </div>
  )
}
