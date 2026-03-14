/**
 * Admin Security Tab
 *
 * Displays fail2ban banned IPs with geolocation data.
 * Data is cached hourly by the backend ban monitor.
 */

import { useState, useEffect } from 'react'
import { ShieldBan, RefreshCw, Globe, Clock, Unlock } from 'lucide-react'
import { adminApi, type BanSnapshot } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminSecurity() {
  const [data, setData] = useState<BanSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const confirm = useConfirm()

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await adminApi.getBans())
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load ban data')
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      setData(await adminApi.refreshBans())
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to refresh ban data')
    } finally {
      setRefreshing(false)
    }
  }

  const handleUnban = async (ip: string) => {
    const ok = await confirm({
      title: 'Unban IP',
      message: `Are you sure you want to unban ${ip}? This IP will be able to access the server again.`,
      confirmLabel: 'Unban',
      variant: 'warning',
    })
    if (!ok) return
    try {
      await adminApi.unbanIp(ip)
      // Refresh to show updated list
      setData(await adminApi.getBans())
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to unban IP')
    }
  }

  useEffect(() => { fetchData() }, [])

  if (loading && !data) {
    return <div className="text-center text-slate-400 py-8">Loading security data...</div>
  }

  return (
    <div className="space-y-5">
      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Currently Banned" value={data.currently_banned} color="text-red-400" />
          <StatCard label="Total Banned" value={data.total_banned} color="text-amber-400" />
          <StatCard label="Total Failed Attempts" value={data.total_failed} color="text-slate-300" />
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-3">
            <p className="text-xs text-slate-500 mb-1">Last Updated</p>
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <p className="text-sm text-slate-300">
                {data.last_updated
                  ? new Date(data.last_updated + 'Z').toLocaleTimeString()
                  : 'Not yet'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <ShieldBan className="w-4 h-4 text-red-400" />
          Banned IPs
        </h3>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 hover:text-blue-300 hover:bg-slate-700 rounded transition-colors disabled:opacity-50"
          title="Query fail2ban now"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh Now'}
        </button>
      </div>

      {/* Banned IPs table */}
      {data && data.banned_ips.length > 0 ? (
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          {/* Desktop table */}
          <table className="w-full text-sm hidden sm:table">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                <th className="text-left p-3">IP Address</th>
                <th className="text-left p-3">Location</th>
                <th className="text-left p-3">ISP / Org</th>
                <th className="text-left p-3">Jail</th>
                <th className="text-right p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.banned_ips.map((ban, i) => (
                <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="p-3">
                    <code className="text-red-400 text-xs font-mono">{ban.ip}</code>
                    {ban.hostname && (
                      <p className="text-xs text-slate-500 truncate max-w-[200px]">{ban.hostname}</p>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      <div>
                        <p className="text-slate-200 text-xs">
                          {[ban.city, ban.region, ban.country].filter(Boolean).join(', ') || 'Unknown'}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-xs text-slate-400 max-w-[200px] truncate">
                    {ban.org || '—'}
                  </td>
                  <td className="p-3">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-900/30 text-red-400">{ban.jail}</span>
                  </td>
                  <td className="p-3 text-right">
                    <button
                      onClick={() => handleUnban(ban.ip)}
                      className="p-1 text-slate-500 hover:text-amber-400 hover:bg-slate-700 rounded transition-colors"
                      title="Unban this IP"
                    >
                      <Unlock className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Mobile cards */}
          <div className="sm:hidden divide-y divide-slate-700/50">
            {data.banned_ips.map((ban, i) => (
              <div key={i} className="p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <code className="text-red-400 text-xs font-mono">{ban.ip}</code>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-900/30 text-red-400">{ban.jail}</span>
                    <button onClick={() => handleUnban(ban.ip)} className="p-1 text-slate-500 hover:text-amber-400" title="Unban">
                      <Unlock className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <p className="text-xs text-slate-300">
                  {[ban.city, ban.region, ban.country].filter(Boolean).join(', ') || 'Unknown'}
                </p>
                {ban.org && <p className="text-xs text-slate-500 truncate">{ban.org}</p>}
                {ban.hostname && <p className="text-xs text-slate-600 truncate">{ban.hostname}</p>}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 text-center text-slate-500 text-sm">
          {data?.last_updated ? 'No banned IPs' : 'Ban monitor has not run yet — data will appear within a minute'}
        </div>
      )}

      <p className="text-xs text-slate-600">
        Ban data refreshes automatically every hour. All bans are full DROP (all ports, all protocols including ICMP) with a 2-year duration.
      </p>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-3">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
    </div>
  )
}
