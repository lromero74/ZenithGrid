import { lazy, Suspense, useEffect, useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Routes, Route, Link, useLocation, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, Settings as SettingsIcon, TrendingUp, DollarSign, Bot, BarChart3, Wallet, History, Newspaper, LogOut, AlertTriangle, X, Sun, Snowflake, Leaf, Sprout, Truck } from 'lucide-react'
import { useMarketSeason } from './hooks/useMarketSeason'
import { positionsApi, authFetch } from './services/api'
import { AccountSwitcher } from './components/AccountSwitcher'
import { PaperTradingToggle } from './components/PaperTradingToggle'
import { AddAccountModal } from './components/AddAccountModal'
import { LoadingSpinner } from './components/LoadingSpinner'
import { NotificationProvider } from './contexts/NotificationContext'
import { VideoPlayerProvider } from './contexts/VideoPlayerContext'
import { ArticleReaderProvider } from './contexts/ArticleReaderContext'
import { AccountProvider, useAccount } from './contexts/AccountContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { BrandProvider, useBrand } from './contexts/BrandContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { MiniPlayer } from './components/MiniPlayer'
import { ArticleReaderMiniPlayer } from './components/ArticleReaderMiniPlayer'
import { RiskDisclaimer } from './components/RiskDisclaimer'
import { AboutModal } from './components/AboutModal'
import { EmailVerificationPending } from './components/EmailVerificationPending'
import { MFAEncouragement, MFA_DISMISSED_KEY } from './components/MFAEncouragement'
import { VerifyEmail } from './components/VerifyEmail'
import { ResetPassword } from './components/ResetPassword'
import MFAEmailVerify from './components/MFAEmailVerify'
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
  const { brand } = useBrand()
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [showAboutModal, setShowAboutModal] = useState(false)
  const [appVersion, setAppVersion] = useState<string>('...')
  const [latestVersion, setLatestVersion] = useState<string | null>(null)
  const [updateAvailable, setUpdateAvailable] = useState(false)

  // Get market season for header display
  const { seasonInfo, headerGradient } = useMarketSeason()

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
        const response = await authFetch('/api/auth/preferences/last-seen-history')
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
  // Falls back to singular endpoint if selectedAccount hasn't resolved yet
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio', selectedAccount?.id],
    queryFn: async () => {
      if (selectedAccount) {
        const response = await authFetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      const response = await authFetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000, // Update prices every 2 minutes
    staleTime: 60000, // Consider data fresh for 60 seconds
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
    placeholderData: keepPreviousData, // Retain old values during refetch instead of flashing to 0
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0

  // Fetch BTC/USD price directly from market data (not calculated from portfolio)
  // This ensures correct price display regardless of paper trading balances
  const { data: btcPriceData } = useQuery({
    queryKey: ['btc-usd-price'],
    queryFn: async () => {
      const response = await authFetch('/api/market/btc-usd-price')
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
      const response = await authFetch('/api/market/eth-usd-price')
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
    refetchInterval: 60000, // Check every 60 seconds (reduced from 10s to save memory)
    enabled: deferredQueriesEnabled, // Defer until 2s after initial render
  })

  const { data: failedPositions = [] } = useQuery({
    queryKey: ['failed-positions-badge'],
    queryFn: () => positionsApi.getAll('failed', 100),
    refetchInterval: 60000, // Check every 60 seconds (reduced from 10s to save memory)
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
          const response = await authFetch('/api/auth/preferences/last-seen-history')
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
        <div className={`border-b border-slate-700 bg-gradient-to-r ${headerGradient} transition-colors duration-1000`}>
          <div className="container mx-auto px-4 sm:px-6 py-3 sm:py-4">
            {/* Desktop layout */}
            <div className="hidden sm:flex flex-row items-center justify-between">
              <div className="flex items-center space-x-3">
                <Truck className="w-8 h-8 text-theme-primary" />
                <div>
                  <h1 className="text-2xl font-bold">{brand.shortName}</h1>
                  <p className="text-sm text-slate-400">
                    {brand.tagline}{' '}
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

              {/* Market Season Indicator - desktop standalone */}
              {seasonInfo && (
                <div className={`hidden lg:flex items-center space-x-1.5 px-3 py-2 mr-6 rounded-lg border ${
                  seasonInfo.season === 'accumulation' ? 'bg-pink-900/30 border-pink-700/50' :
                  seasonInfo.season === 'bull' ? 'bg-green-900/30 border-green-700/50' :
                  seasonInfo.season === 'distribution' ? 'bg-orange-900/30 border-orange-700/50' :
                  'bg-blue-900/30 border-blue-700/50'
                }`} title={`${seasonInfo.subtitle}: ${seasonInfo.description}`}>
                  {seasonInfo.season === 'accumulation' && <Sprout className="w-4 h-4 text-pink-400" />}
                  {seasonInfo.season === 'bull' && <Sun className="w-4 h-4 text-green-400" />}
                  {seasonInfo.season === 'distribution' && <Leaf className="w-4 h-4 text-orange-400" />}
                  {seasonInfo.season === 'bear' && <Snowflake className="w-4 h-4 text-blue-400" />}
                  <span className={`text-sm font-medium ${seasonInfo.color}`}>{seasonInfo.name}</span>
                </div>
              )}

              <div className="flex items-center gap-3 md:gap-6">
                {/* Season - tablet only (sm to lg) */}
                {seasonInfo && (
                  <div className={`flex lg:hidden items-center space-x-1.5 px-3 py-2 rounded-lg border ${
                    seasonInfo.season === 'accumulation' ? 'bg-pink-900/30 border-pink-700/50' :
                    seasonInfo.season === 'bull' ? 'bg-green-900/30 border-green-700/50' :
                    seasonInfo.season === 'distribution' ? 'bg-orange-900/30 border-orange-700/50' :
                    'bg-blue-900/30 border-blue-700/50'
                  }`} title={`${seasonInfo.subtitle}: ${seasonInfo.description}`}>
                    {seasonInfo.season === 'accumulation' && <Sprout className="w-4 h-4 text-pink-400" />}
                    {seasonInfo.season === 'bull' && <Sun className="w-4 h-4 text-green-400" />}
                    {seasonInfo.season === 'distribution' && <Leaf className="w-4 h-4 text-orange-400" />}
                    {seasonInfo.season === 'bear' && <Snowflake className="w-4 h-4 text-blue-400" />}
                    <span className={`text-sm font-medium ${seasonInfo.color}`}>{seasonInfo.name}</span>
                  </div>
                )}
                <PaperTradingToggle />
                <div className="hidden md:block">
                  <AccountSwitcher
                    onAddAccount={() => setShowAddAccountModal(true)}
                    onManageAccounts={() => navigate('/settings')}
                  />
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">BTC Price</p>
                  <p className="text-sm font-medium text-orange-400">
                    ${btcUsdPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </p>
                  <p className="text-xs text-slate-500">
                    {usdBtcPrice.toFixed(8)} BTC/USD
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">ETH Price</p>
                  <p className="text-sm font-medium text-blue-400">
                    ${ethUsdPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </p>
                  <p className="text-xs text-slate-500">
                    {usdEthPrice.toFixed(8)} ETH/USD
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-slate-400">Account Value</p>
                  {!portfolio ? (
                    <>
                      <div className="h-7 w-32 bg-slate-700 rounded animate-pulse ml-auto" />
                      <div className="h-5 w-16 bg-slate-700 rounded animate-pulse ml-auto mt-1" />
                    </>
                  ) : (
                    <>
                      <p className="text-xl font-bold text-blue-400">
                        {totalBtcValue.toFixed(6)} BTC
                      </p>
                      <p className="text-sm text-green-400">
                        ${totalUsdValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </>
                  )}
                </div>
                <DollarSign className="w-8 h-8 md:w-10 md:h-10 text-green-500 opacity-50" />
                <div className="flex items-center space-x-2 pl-4 border-l border-slate-600">
                  <div className="text-right">
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

            {/* Mobile layout */}
            <div className="flex sm:hidden flex-col gap-2">
              {/* Row 1: Brand left, Account Value right */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Truck className="w-6 h-6 text-theme-primary" />
                  <div>
                    <h1 className="text-lg font-bold leading-tight">{brand.shortName}</h1>
                    <button
                      onClick={() => setShowAboutModal(true)}
                      className={`text-[10px] ${updateAvailable ? 'text-yellow-500' : 'text-slate-500'} hover:text-blue-400 transition-colors`}
                      title="Click to view changelog"
                    >
                      {appVersion}
                      {updateAvailable && (
                        <span className="ml-1 text-green-400">
                          → {latestVersion}
                        </span>
                      )}
                    </button>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-[10px] text-slate-400 leading-tight">Account Value</p>
                  {!portfolio ? (
                    <>
                      <div className="h-5 w-28 bg-slate-700 rounded animate-pulse ml-auto" />
                      <div className="h-4 w-14 bg-slate-700 rounded animate-pulse ml-auto mt-0.5" />
                    </>
                  ) : (
                    <>
                      <p className="text-base font-bold text-blue-400 leading-tight">
                        {totalBtcValue.toFixed(6)} BTC
                      </p>
                      <p className="text-xs text-green-400 leading-tight">
                        ${totalUsdValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* Row 2: Controls bar — evenly spaced, equal-height pills */}
              <div className="flex items-stretch justify-between gap-1.5 pt-1.5 border-t border-slate-700/50">
                {/* Season */}
                {seasonInfo && (
                  <div className={`flex items-center space-x-1 px-2 rounded-lg border ${
                    seasonInfo.season === 'accumulation' ? 'bg-pink-900/30 border-pink-700/50' :
                    seasonInfo.season === 'bull' ? 'bg-green-900/30 border-green-700/50' :
                    seasonInfo.season === 'distribution' ? 'bg-orange-900/30 border-orange-700/50' :
                    'bg-blue-900/30 border-blue-700/50'
                  }`} title={`${seasonInfo.subtitle}: ${seasonInfo.description}`}>
                    {seasonInfo.season === 'accumulation' && <Sprout className="w-3.5 h-3.5 text-pink-400" />}
                    {seasonInfo.season === 'bull' && <Sun className="w-3.5 h-3.5 text-green-400" />}
                    {seasonInfo.season === 'distribution' && <Leaf className="w-3.5 h-3.5 text-orange-400" />}
                    {seasonInfo.season === 'bear' && <Snowflake className="w-3.5 h-3.5 text-blue-400" />}
                    <span className={`text-[11px] font-medium ${seasonInfo.color}`}>{seasonInfo.name}</span>
                  </div>
                )}

                {/* Paper/Live Toggle */}
                <PaperTradingToggle />

                {/* Account Switcher */}
                <AccountSwitcher
                  onAddAccount={() => setShowAddAccountModal(true)}
                  onManageAccounts={() => navigate('/settings')}
                />

                {/* Logout */}
                <button
                  onClick={() => setShowLogoutConfirm(true)}
                  className="flex items-center px-2 text-slate-400 hover:text-red-400 bg-slate-700 hover:bg-slate-600 rounded-lg border border-slate-600 transition-colors"
                  title="Sign Out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
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
            <div className="hidden sm:flex items-center px-1">
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
          <p className="text-xs text-slate-600 mt-1">
            Powered by <span className="text-slate-500">Zenith Grid</span>: a Romero Tech Solutions Open Source Project
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

// Verify Email route handler (works regardless of auth state)
function VerifyEmailRoute() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  if (!token) {
    return <Navigate to="/" replace />
  }

  return (
    <VerifyEmail
      token={token}
      onComplete={() => navigate('/', { replace: true })}
    />
  )
}

// MFA Email Verify route handler (works regardless of auth state)
function MFAEmailVerifyRoute() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  if (!token) {
    return <Navigate to="/" replace />
  }

  return (
    <MFAEmailVerify
      token={token}
      onComplete={() => navigate('/', { replace: true })}
    />
  )
}

// Reset Password route handler (works regardless of auth state)
function ResetPasswordRoute() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  if (!token) {
    return <Navigate to="/" replace />
  }

  return (
    <ResetPassword
      token={token}
      onComplete={() => navigate('/', { replace: true })}
    />
  )
}

// Root App component - handles authentication wrapper
function App() {
  const { isAuthenticated, isLoading, user, acceptTerms, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [isAcceptingTerms, setIsAcceptingTerms] = useState(false)
  const [mfaDismissed, setMfaDismissed] = useState(
    () => localStorage.getItem(MFA_DISMISSED_KEY) === 'true'
  )

  // Handle special routes that work regardless of auth state
  if (location.pathname === '/verify-email') {
    return <VerifyEmailRoute />
  }
  if (location.pathname === '/reset-password') {
    return <ResetPasswordRoute />
  }
  if (location.pathname === '/mfa-email-verify') {
    return <MFAEmailVerifyRoute />
  }

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

  // Gate: Email verification required
  if (user && !user.email_verified) {
    return <EmailVerificationPending />
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

  // Gate: MFA encouragement (one time, after email verified + terms accepted)
  if (user && !user.mfa_enabled && !user.mfa_email_enabled && !mfaDismissed) {
    return (
      <MFAEncouragement
        onSetupMFA={() => {
          setMfaDismissed(true)
          navigate('/settings')
        }}
        onSkip={() => setMfaDismissed(true)}
      />
    )
  }

  // Show main app content (AccountProvider here ensures accounts fetch only after auth)
  return (
    <AccountProvider>
      <AppContent />
    </AccountProvider>
  )
}

// Export with AuthProvider wrapper
function AppWithAuth() {
  return (
    <BrandProvider>
      <ThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ThemeProvider>
    </BrandProvider>
  )
}

export default AppWithAuth
