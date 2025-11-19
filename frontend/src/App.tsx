import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
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

type Page = 'dashboard' | 'bots' | 'positions' | 'closedPositions' | 'portfolio' | 'charts' | 'strategies' | 'settings'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>(() => {
    // Restore last viewed page from localStorage
    const saved = localStorage.getItem('current-page')
    return (saved as Page) || 'dashboard'
  })

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
    refetchInterval: 60000, // Update prices every 60 seconds
    staleTime: 30000, // Consider data fresh for 30 seconds
    refetchOnMount: false, // Don't refetch on page refresh - use cache
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0

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

  // Save current page to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('current-page', currentPage)

    // Mark closed positions as viewed when navigating to History page
    if (currentPage === 'closedPositions') {
      const now = Date.now()
      setLastViewedClosedPositions(now)
      localStorage.setItem('last-viewed-closed-positions', now.toString())
    }
  }, [currentPage])

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
            <button
              onClick={() => setCurrentPage('dashboard')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'dashboard'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Activity className="w-4 h-4" />
                <span className="hidden sm:inline">Dashboard</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('bots')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'bots'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Bot className="w-4 h-4" />
                <span className="hidden sm:inline">Bots</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('positions')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'positions'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <TrendingUp className="w-4 h-4" />
                <span className="hidden sm:inline">Positions</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('closedPositions')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base relative ${
                currentPage === 'closedPositions'
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
            </button>
            <button
              onClick={() => setCurrentPage('portfolio')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'portfolio'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Wallet className="w-4 h-4" />
                <span className="hidden sm:inline">Portfolio</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('charts')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'charts'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <BarChart3 className="w-4 h-4" />
                <span className="hidden sm:inline">Charts</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('strategies')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'strategies'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Layers className="w-4 h-4" />
                <span className="hidden sm:inline">Strategies</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('settings')}
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                currentPage === 'settings'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <SettingsIcon className="w-4 h-4" />
                <span className="hidden sm:inline">Settings</span>
              </div>
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 sm:px-6 py-4 sm:py-8">
        {currentPage === 'dashboard' && <Dashboard onNavigate={setCurrentPage} />}
        {currentPage === 'bots' && <Bots />}
        {currentPage === 'positions' && <Positions />}
        {currentPage === 'closedPositions' && <ClosedPositions />}
        {currentPage === 'portfolio' && <Portfolio />}
        {currentPage === 'charts' && <Charts />}
        {currentPage === 'strategies' && <Strategies />}
        {currentPage === 'settings' && <Settings />}
      </main>
    </div>
  )
}

export default App
