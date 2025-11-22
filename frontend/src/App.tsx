import { useQuery } from '@tanstack/react-query'
import { Routes, Route, Link, useLocation, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Positions from './pages/Positions'
import ClosedPositions from './pages/ClosedPositions'
import Bots from './pages/Bots'
import Charts from './pages/Charts'
import Strategies from './pages/Strategies'
import Portfolio from './pages/Portfolio'
import { Activity, Settings as SettingsIcon, TrendingUp, DollarSign, Bot, BarChart3, Layers, Wallet, History } from 'lucide-react'
import { positionsApi } from './services/api'
import { useEffect, useState } from 'react'

function App() {
  const location = useLocation()

  // Track last viewed timestamp for closed positions
  const [lastViewedClosedPositions, setLastViewedClosedPositions] = useState<number>(() => {
    const saved = localStorage.getItem('last-viewed-closed-positions')
    return saved ? parseInt(saved) : Date.now()
  })

  // Fetch full portfolio data (all coins)
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio'],
    queryFn: async () => {
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000, // Update prices every 2 minutes
    staleTime: 60000, // Consider data fresh for 60 seconds
    refetchOnMount: false, // Don't refetch on page refresh - use cache
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0

  // Calculate BTC/USD price from portfolio data
  const btcUsdPrice = totalBtcValue > 0 ? totalUsdValue / totalBtcValue : 0
  const usdBtcPrice = btcUsdPrice > 0 ? 1 / btcUsdPrice : 0

  // Fetch closed positions to count new ones
  const { data: closedPositions = [] } = useQuery({
    queryKey: ['closed-positions-badge'],
    queryFn: () => positionsApi.getAll('closed', 100),
    refetchInterval: 10000, // Check every 10 seconds
  })

  // Count new closed positions since last view
  const newClosedCount = closedPositions.filter(pos => {
    const closedAt = new Date(pos.closed_at || pos.opened_at).getTime()
    return closedAt > lastViewedClosedPositions
  }).length

  // Mark closed positions as viewed after a few seconds on History page
  useEffect(() => {
    if (location.pathname === '/history') {
      console.log('🔴 History page opened, setting 3s timer')
      const timer = setTimeout(() => {
        const now = Date.now()
        console.log('✅ Timer fired! Clearing badge notification')
        setLastViewedClosedPositions(now)
        localStorage.setItem('last-viewed-closed-positions', now.toString())
      }, 3000) // Clear badge after 3 seconds

      // Cleanup timer if user navigates away before it completes
      return () => {
        console.log('🧹 Cleaning up timer (page navigation)')
        clearTimeout(timer)
      }
    }
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700">
        <div className="container mx-auto px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-0">
            <div className="flex items-center space-x-2 sm:space-x-3">
              <Activity className="w-6 h-6 sm:w-8 sm:h-8 text-blue-500" />
              <div>
                <h1 className="text-xl sm:text-2xl font-bold">Zenith Grid</h1>
                <p className="text-xs sm:text-sm text-slate-400 hidden sm:block">Multi-Strategy Trading Platform</p>
              </div>
            </div>
            <div className="flex items-center space-x-3 sm:space-x-6 self-end sm:self-auto">
              <div className="text-right hidden sm:block">
                <p className="text-xs text-slate-400">BTC Price</p>
                <p className="text-sm font-medium text-orange-400">
                  ${btcUsdPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-slate-500">
                  {usdBtcPrice.toFixed(8)} BTC/USD
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs sm:text-sm text-slate-400">Account Value</p>
                <p className="text-base sm:text-xl font-bold text-blue-400">
                  {totalBtcValue.toFixed(6)} BTC
                </p>
                <p className="text-xs sm:text-sm text-green-400">
                  ${totalUsdValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <DollarSign className="w-8 h-8 sm:w-10 sm:h-10 text-green-500 opacity-50" />
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-slate-800 border-b border-slate-700 overflow-x-auto">
        <div className="container mx-auto px-4 sm:px-6">
          <div className="flex space-x-1 min-w-max sm:min-w-0">
            <Link
              to="/"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Activity className="w-4 h-4" />
                <span className="hidden sm:inline">Dashboard</span>
              </div>
            </Link>
            <Link
              to="/bots"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/bots'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Bot className="w-4 h-4" />
                <span className="hidden sm:inline">Bots</span>
              </div>
            </Link>
            <Link
              to="/positions"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/positions'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <TrendingUp className="w-4 h-4" />
                <span className="hidden sm:inline">Positions</span>
              </div>
            </Link>
            <Link
              to="/history"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base relative ${
                location.pathname === '/history'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <History className="w-4 h-4" />
                <span className="hidden sm:inline">History</span>
                {newClosedCount > 0 && (
                  <span className="absolute -top-1 -right-1 sm:relative sm:top-0 sm:right-0 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                    {newClosedCount > 9 ? '9+' : newClosedCount}
                  </span>
                )}
              </div>
            </Link>
            <Link
              to="/portfolio"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/portfolio'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Wallet className="w-4 h-4" />
                <span className="hidden sm:inline">Portfolio</span>
              </div>
            </Link>
            <Link
              to="/charts"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/charts'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <BarChart3 className="w-4 h-4" />
                <span className="hidden sm:inline">Charts</span>
              </div>
            </Link>
            <Link
              to="/strategies"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/strategies'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Layers className="w-4 h-4" />
                <span className="hidden sm:inline">Strategies</span>
              </div>
            </Link>
            <Link
              to="/settings"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/settings'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <SettingsIcon className="w-4 h-4" />
                <span className="hidden sm:inline">Settings</span>
              </div>
            </Link>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 sm:px-6 py-4 sm:py-8">
        <Routes>
          <Route path="/" element={<Dashboard onNavigate={(page) => {}} />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/history" element={<ClosedPositions />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/charts" element={<Charts />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/settings" element={<Settings />} />
          {/* Redirect unknown routes to dashboard */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
