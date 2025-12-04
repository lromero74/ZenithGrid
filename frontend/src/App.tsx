import { lazy, Suspense, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { Activity, Settings as SettingsIcon, TrendingUp, DollarSign, Bot, BarChart3, Layers, Wallet, History, Newspaper, LogOut } from 'lucide-react'
import { positionsApi } from './services/api'
import { AccountSwitcher } from './components/AccountSwitcher'
import { AddAccountModal } from './components/AddAccountModal'
import { LoadingSpinner } from './components/LoadingSpinner'
import { NotificationProvider } from './contexts/NotificationContext'
import { useAccount } from './contexts/AccountContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Login from './pages/Login'

// Lazy load pages for faster initial render
// Dashboard is eager-loaded since it's the landing page
import Dashboard from './pages/Dashboard'
const Settings = lazy(() => import('./pages/Settings'))
const Positions = lazy(() => import('./pages/Positions'))
const ClosedPositions = lazy(() => import('./pages/ClosedPositions'))
const Bots = lazy(() => import('./pages/Bots'))
const Charts = lazy(() => import('./pages/Charts'))
const Strategies = lazy(() => import('./pages/Strategies'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const News = lazy(() => import('./pages/News'))

// Main App content (shown when authenticated)
function AppContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const { selectedAccount } = useAccount()
  const { user, logout } = useAuth()
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)

  // Track last seen count of history items (closed + failed)
  const [lastSeenHistoryCount, setLastSeenHistoryCount] = useState<number>(() => {
    const saved = localStorage.getItem('last-seen-history-count')
    return saved ? parseInt(saved) : 0
  })

  // Defer non-critical API calls until after initial render
  const [deferredQueriesEnabled, setDeferredQueriesEnabled] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setDeferredQueriesEnabled(true), 2000) // Enable after 2s
    return () => clearTimeout(timer)
  }, [])

  // Fetch full portfolio data (all coins) - account-specific for CEX/DEX switching
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio', selectedAccount?.id],
    queryFn: async () => {
      // If we have a selected account, use the account-specific endpoint
      if (selectedAccount) {
        const response = await fetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      // Fallback to legacy endpoint
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

  // Fetch closed and failed positions to count total history items (deferred)
  const { data: closedPositions = [] } = useQuery({
    queryKey: ['closed-positions-badge'],
    queryFn: () => positionsApi.getAll('closed', 100),
    refetchInterval: 10000, // Check every 10 seconds
    enabled: deferredQueriesEnabled, // Defer until 2s after initial render
  })

  const { data: failedPositions = [] } = useQuery({
    queryKey: ['failed-positions-badge'],
    queryFn: () => positionsApi.getAll('failed', 100),
    refetchInterval: 10000, // Check every 10 seconds
    enabled: deferredQueriesEnabled, // Defer until 2s after initial render
  })

  // Calculate total history count and badge delta
  const currentHistoryCount = closedPositions.length + failedPositions.length
  const newHistoryItemsCount = Math.max(0, currentHistoryCount - lastSeenHistoryCount)

  // Mark history as viewed after a few seconds on History page
  useEffect(() => {
    if (location.pathname === '/history') {
      console.log('🔴 History page opened, setting 3s timer')
      const timer = setTimeout(() => {
        console.log('✅ Timer fired! Updating last seen count from', lastSeenHistoryCount, 'to', currentHistoryCount)
        setLastSeenHistoryCount(currentHistoryCount)
        localStorage.setItem('last-seen-history-count', currentHistoryCount.toString())
      }, 3000) // Clear badge after 3 seconds

      // Cleanup timer if user navigates away before it completes
      return () => {
        console.log('🧹 Cleaning up timer (page navigation)')
        clearTimeout(timer)
      }
    }
  }, [location.pathname, currentHistoryCount, lastSeenHistoryCount])

  return (
    <NotificationProvider>
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
              {/* Account Switcher */}
              <AccountSwitcher
                onAddAccount={() => setShowAddAccountModal(true)}
                onManageAccounts={() => navigate('/settings')}
              />

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

              {/* User Info & Logout */}
              <div className="flex items-center space-x-2 pl-4 border-l border-slate-600">
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-slate-400">Logged in as</p>
                  <p className="text-sm text-slate-200">{user?.display_name || user?.email}</p>
                </div>
                <button
                  onClick={logout}
                  className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors"
                  title="Sign Out"
                >
                  <LogOut className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-slate-800 border-b border-slate-700 overflow-x-auto">
        <div className="container mx-auto px-4 sm:px-6">
          <div className="flex space-x-1 min-w-max sm:min-w-0">
            {/* Account-Specific Pages */}
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
                {newHistoryItemsCount > 0 && (
                  <span className="absolute -top-1 -right-1 sm:relative sm:top-0 sm:right-0 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                    {newHistoryItemsCount > 9 ? '9+' : newHistoryItemsCount}
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

            {/* Separator */}
            <div className="flex items-center px-1">
              <div className="h-6 w-px bg-slate-600" />
            </div>

            {/* General Pages */}
            <Link
              to="/news"
              className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
                location.pathname === '/news'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-1 sm:space-x-2">
                <Newspaper className="w-4 h-4" />
                <span className="hidden sm:inline">News</span>
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
        <Suspense fallback={
          <div className="flex items-center justify-center min-h-[400px]">
            <LoadingSpinner size="lg" text="Loading..." />
          </div>
        }>
          <Routes>
            <Route path="/" element={<Dashboard onNavigate={() => {}} />} />
            <Route path="/bots" element={<Bots />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/history" element={<ClosedPositions />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/news" element={<News />} />
            <Route path="/charts" element={<Charts />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/settings" element={<Settings />} />
            {/* Redirect unknown routes to dashboard */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>

      {/* Footer */}
      <footer className="bg-slate-800 border-t border-slate-700 py-4 mt-8">
        <div className="container mx-auto px-4 sm:px-6 text-center">
          <p className="text-sm text-slate-400">
            &copy; {new Date().getFullYear()} Romero Tech Solutions. All rights reserved.
          </p>
        </div>
      </footer>

      {/* Add Account Modal */}
      <AddAccountModal
        isOpen={showAddAccountModal}
        onClose={() => setShowAddAccountModal(false)}
      />
    </div>
    </NotificationProvider>
  )
}

// Root App component - handles authentication wrapper
function App() {
  const { isAuthenticated, isLoading } = useAuth()

  // Show loading spinner while checking auth state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <LoadingSpinner size="lg" text="Loading..." />
      </div>
    )
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <Login />
  }

  // Show main app content
  return <AppContent />
}

// Export with AuthProvider wrapper
function AppWithAuth() {
  return (
    <AuthProvider>
      <App />
    </AuthProvider>
  )
}

export default AppWithAuth
