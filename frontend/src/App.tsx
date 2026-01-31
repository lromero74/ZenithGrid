import { lazy, Suspense, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { Activity, Settings as SettingsIcon, TrendingUp, DollarSign, Bot, BarChart3, Wallet, History, Newspaper, LogOut, AlertTriangle, X } from 'lucide-react'
import { positionsApi } from './services/api'
import { AccountSwitcher } from './components/AccountSwitcher'
import { PaperTradingToggle } from './components/PaperTradingToggle'
import { AddAccountModal } from './components/AddAccountModal'
import { LoadingSpinner } from './components/LoadingSpinner'
import { NotificationProvider } from './contexts/NotificationContext'
import { VideoPlayerProvider } from './contexts/VideoPlayerContext'
import { ArticleReaderProvider } from './contexts/ArticleReaderContext'
import { useAccount } from './contexts/AccountContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { MiniPlayer } from './components/MiniPlayer'
import { ArticleReaderMiniPlayer } from './components/ArticleReaderMiniPlayer'
import { RiskDisclaimer } from './components/RiskDisclaimer'
import { AboutModal } from './components/AboutModal'
import Login from './pages/Login'

// App version - fetched from backend API at runtime (avoids Vite cache issues)

// Lazy load pages for faster initial render
// Dashboard is eager-loaded since it's the landing page
import Dashboard from './pages/Dashboard'
const Settings = lazy(() => import('./pages/Settings'))
const Positions = lazy(() => import('./pages/Positions'))
const ClosedPositions = lazy(() => import('./pages/ClosedPositions'))
const Bots = lazy(() => import('./pages/Bots'))
const Charts = lazy(() => import('./pages/Charts'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const News = lazy(() => import('./pages/News'))

// Main App content (shown when authenticated)
function AppContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const { selectedAccount } = useAccount()
  const { user, logout, getAccessToken } = useAuth()
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [showAboutModal, setShowAboutModal] = useState(false)
  const [appVersion, setAppVersion] = useState<string>('...')
  const [latestVersion, setLatestVersion] = useState<string | null>(null)
  const [updateAvailable, setUpdateAvailable] = useState(false)

  // Fetch version from backend root endpoint (runs once on app load)
  // Using root / endpoint since it's guaranteed to work (also serves as health check)
  useEffect(() => {
    fetch('/api/')
      .then(res => res.json())
      .then(data => {
        setAppVersion(data.version || 'dev')
        setLatestVersion(data.latest_version || null)
        setUpdateAvailable(data.update_available || false)
      })
      .catch(() => setAppVersion('dev'))
  }, [])

  // Track last seen counts for history items (separate for closed and failed) - fetched from server
  const [lastSeenClosedCount, setLastSeenClosedCount] = useState<number>(0)
  const [lastSeenFailedCount, setLastSeenFailedCount] = useState<number>(0)

  // Fetch last seen history counts from server on mount
  useEffect(() => {
    const fetchLastSeenCounts = async () => {
      const token = getAccessToken()
      if (!token) return

      try {
        const response = await fetch('/api/auth/preferences/last-seen-history', {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (response.ok) {
          const data = await response.json()
          setLastSeenClosedCount(data.last_seen_history_count || 0)
          setLastSeenFailedCount(data.last_seen_failed_count || 0)
        }
      } catch (error) {
        console.error('Failed to fetch last seen history counts:', error)
      }
    }

    fetchLastSeenCounts()
  }, [getAccessToken])

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

  // Fetch BTC/USD price directly from market data (not calculated from portfolio)
  // This ensures correct price display regardless of paper trading balances
  const { data: btcPriceData } = useQuery({
    queryKey: ['btc-usd-price'],
    queryFn: async () => {
      const response = await fetch('/api/market/btc-usd-price')
      if (!response.ok) throw new Error('Failed to fetch BTC price')
      return response.json()
    },
    refetchInterval: 60000, // Update every 60 seconds
    staleTime: 30000, // Consider data fresh for 30 seconds
  })

  const btcUsdPrice = btcPriceData?.price || 0
  const usdBtcPrice = btcUsdPrice > 0 ? 1 / btcUsdPrice : 0

  // Fetch ETH/USD price directly from market data
  const { data: ethPriceData } = useQuery({
    queryKey: ['eth-usd-price'],
    queryFn: async () => {
      const response = await fetch('/api/market/eth-usd-price')
      if (!response.ok) throw new Error('Failed to fetch ETH price')
      return response.json()
    },
    refetchInterval: 60000, // Update every 60 seconds
    staleTime: 30000, // Consider data fresh for 30 seconds
  })

  const ethUsdPrice = ethPriceData?.price || 0
  const usdEthPrice = ethUsdPrice > 0 ? 1 / ethUsdPrice : 0

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

  // Calculate badge counts separately for closed and failed
  const currentClosedCount = closedPositions.length
  const currentFailedCount = failedPositions.length
  const newClosedItemsCount = Math.max(0, currentClosedCount - lastSeenClosedCount)
  const newFailedItemsCount = Math.max(0, currentFailedCount - lastSeenFailedCount)
  // Header badge shows combined total of unseen items from both categories
  const newHistoryItemsCount = newClosedItemsCount + newFailedItemsCount

  // Refetch last seen counts when navigating to History page
  // This ensures App.tsx stays in sync after ClosedPositions.tsx clears individual counts
  useEffect(() => {
    if (location.pathname === '/history') {
      const refetchCounts = async () => {
        const token = getAccessToken()
        if (!token) return

        try {
          const response = await fetch('/api/auth/preferences/last-seen-history', {
            headers: { 'Authorization': `Bearer ${token}` }
          })
          if (response.ok) {
            const data = await response.json()
            setLastSeenClosedCount(data.last_seen_history_count || 0)
            setLastSeenFailedCount(data.last_seen_failed_count || 0)
          }
        } catch (error) {
          console.error('Failed to refetch last seen history counts:', error)
        }
      }

      // Refetch periodically while on History page to catch updates from ClosedPositions
      const interval = setInterval(refetchCounts, 2000)
      return () => clearInterval(interval)
    }
  }, [location.pathname, getAccessToken])

  return (
    <NotificationProvider>
    <VideoPlayerProvider>
    <ArticleReaderProvider>
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-800">
        <div className="border-b border-slate-700">
          <div className="container mx-auto px-4 sm:px-6 py-3 sm:py-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-0">
              <div className="flex items-center space-x-2 sm:space-x-3">
                <Activity className="w-6 h-6 sm:w-8 sm:h-8 text-blue-500" />
                <div>
                  <h1 className="text-xl sm:text-2xl font-bold">Zenith Grid</h1>
                  <p className="text-xs sm:text-sm text-slate-400 hidden sm:block">
                    Multi-Strategy Trading Platform{' '}
                    <button
                      onClick={() => setShowAboutModal(true)}
                      className={`${updateAvailable ? 'text-yellow-500' : 'text-slate-500'} hover:text-blue-400 hover:underline transition-colors cursor-pointer`}
                      title="Click to view changelog"
                    >
                      {appVersion}
                    </button>
                    {updateAvailable && (
                      <button
                        onClick={() => setShowAboutModal(true)}
                        className="ml-1 text-green-400 hover:text-green-300 hover:underline transition-colors cursor-pointer"
                        title={`Latest: ${latestVersion} - Click to view changelog`}
                      >
                        ({latestVersion} available)
                      </button>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-3 sm:space-x-6 self-end sm:self-auto">
                {/* Paper Trading Toggle */}
                <PaperTradingToggle />

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
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-slate-400">ETH Price</p>
                  <p className="text-sm font-medium text-blue-400">
                    ${ethUsdPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </p>
                  <p className="text-xs text-slate-500">
                    {usdEthPrice.toFixed(8)} ETH/USD
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
                    onClick={() => setShowLogoutConfirm(true)}
                    className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors"
                    title="Sign Out"
                  >
                    <LogOut className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Paper Trading Mode Indicator */}
        {selectedAccount?.is_paper_trading && (
          <div className="bg-yellow-900/50 border-b border-yellow-600/50">
            <div className="container mx-auto px-4 sm:px-6 py-2">
              <div className="flex items-center justify-center space-x-2 text-yellow-200">
                <AlertTriangle className="w-5 h-5" />
                <span className="text-sm font-medium">
                  Paper Trading Mode - All trades are simulated
                </span>
                <AlertTriangle className="w-5 h-5" />
              </div>
            </div>
          </div>
        )}

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
      </header>

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

      {/* About Modal */}
      <AboutModal
        isOpen={showAboutModal}
        onClose={() => setShowAboutModal(false)}
      />

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-sm bg-slate-800 rounded-lg shadow-2xl border border-slate-700">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5 text-yellow-400" />
                <h3 className="text-lg font-semibold text-white">Confirm Sign Out</h3>
              </div>
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4">
              <p className="text-slate-300 text-sm">
                Are you sure you want to sign out? You will need to log in again to access your account.
              </p>
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end space-x-3 p-4 border-t border-slate-700">
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowLogoutConfirm(false)
                  logout()
                }}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Persistent Mini Video Player */}
      <MiniPlayer />

      {/* Persistent Article Reader Mini Player */}
      <ArticleReaderMiniPlayer />
    </div>
    </ArticleReaderProvider>
    </VideoPlayerProvider>
    </NotificationProvider>
  )
}

// Root App component - handles authentication wrapper
function App() {
  const { isAuthenticated, isLoading, user, acceptTerms, logout } = useAuth()
  const [isAcceptingTerms, setIsAcceptingTerms] = useState(false)

  // Handle terms acceptance
  const handleAcceptTerms = async () => {
    setIsAcceptingTerms(true)
    try {
      await acceptTerms()
    } catch (error) {
      console.error('Failed to accept terms:', error)
    } finally {
      setIsAcceptingTerms(false)
    }
  }

  // Handle terms decline - log the user out
  const handleDeclineTerms = () => {
    logout()
  }

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

  // Show risk disclaimer if user hasn't accepted terms yet
  if (user && !user.terms_accepted_at) {
    return (
      <RiskDisclaimer
        onAccept={handleAcceptTerms}
        onDecline={handleDeclineTerms}
        isLoading={isAcceptingTerms}
      />
    )
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
