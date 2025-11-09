import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Positions from './pages/Positions'
import Bots from './pages/Bots'
import Charts from './pages/Charts'
import Strategies from './pages/Strategies'
import { Activity, Settings as SettingsIcon, TrendingUp, DollarSign, Bot, BarChart3, Layers } from 'lucide-react'
import { accountApi } from './services/api'

type Page = 'dashboard' | 'bots' | 'positions' | 'charts' | 'strategies' | 'settings'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')

  // Fetch account balances (includes BTC/USD price)
  const { data: balances } = useQuery({
    queryKey: ['account-balances'],
    queryFn: accountApi.getBalances,
    refetchInterval: 5000, // Update every 5 seconds
  })

  const totalBtcValue = balances?.total_btc_value || 0
  const totalUsdValue = balances?.total_usd_value || 0

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Activity className="w-8 h-8 text-blue-500" />
              <div>
                <h1 className="text-2xl font-bold">Zenith Grid</h1>
                <p className="text-sm text-slate-400">Multi-Strategy Trading Platform</p>
              </div>
            </div>
            <div className="flex items-center space-x-6">
              <div className="text-right">
                <p className="text-sm text-slate-400">Account Value</p>
                <p className="text-xl font-bold text-blue-400">
                  {totalBtcValue.toFixed(8)} BTC
                </p>
                <p className="text-sm text-green-400">
                  ${totalUsdValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
              </div>
              <DollarSign className="w-10 h-10 text-green-500 opacity-50" />
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-slate-800 border-b border-slate-700">
        <div className="container mx-auto px-6">
          <div className="flex space-x-1">
            <button
              onClick={() => setCurrentPage('dashboard')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'dashboard'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4" />
                <span>Dashboard</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('bots')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'bots'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <Bot className="w-4 h-4" />
                <span>Bots</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('positions')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'positions'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <TrendingUp className="w-4 h-4" />
                <span>Positions</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('charts')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'charts'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <BarChart3 className="w-4 h-4" />
                <span>Charts</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('strategies')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'strategies'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <Layers className="w-4 h-4" />
                <span>Strategies</span>
              </div>
            </button>
            <button
              onClick={() => setCurrentPage('settings')}
              className={`px-4 py-3 font-medium transition-colors ${
                currentPage === 'settings'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2">
                <SettingsIcon className="w-4 h-4" />
                <span>Settings</span>
              </div>
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {currentPage === 'dashboard' && <Dashboard />}
        {currentPage === 'bots' && <Bots />}
        {currentPage === 'positions' && <Positions />}
        {currentPage === 'charts' && <Charts />}
        {currentPage === 'strategies' && <Strategies />}
        {currentPage === 'settings' && <Settings />}
      </main>
    </div>
  )
}

export default App
