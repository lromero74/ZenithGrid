/**
 * Admin Security Tab
 *
 * Displays fail2ban banned IPs with geolocation data, pagination,
 * and visual reports (ban type breakdown, country distribution).
 */

import { useState, useEffect, useMemo } from 'react'
import { ShieldBan, RefreshCw, Globe, Clock, Unlock, ChevronLeft, ChevronRight, BarChart3, X, AlertTriangle } from 'lucide-react'
import { adminApi, type BanSnapshot } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

const PAGE_SIZE = 10

type SubTab = 'bans' | 'report'

export function AdminSecurity() {
  const [data, setData] = useState<BanSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [subTab, setSubTab] = useState<SubTab>('bans')
  const [detailIp, setDetailIp] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<{ ip: string; total_hits: number; categories: Record<string, number>; sample_requests: string[] } | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const confirm = useConfirm()

  const openDetail = async (ip: string) => {
    setDetailIp(ip)
    setDetailLoading(true)
    setDetailData(null)
    try {
      setDetailData(await adminApi.getBanDetails(ip))
    } catch {
      // silently fail
    } finally {
      setDetailLoading(false)
    }
  }

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
      setData(await adminApi.getBans())
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to unban IP')
    }
  }

  useEffect(() => { fetchData() }, [])

  // Pagination
  const totalPages = data ? Math.ceil(data.banned_ips.length / PAGE_SIZE) : 0
  const pagedBans = useMemo(() => {
    if (!data) return []
    const start = page * PAGE_SIZE
    return data.banned_ips.slice(start, start + PAGE_SIZE)
  }, [data, page])

  // Report data
  const jailCounts = useMemo(() => {
    if (!data) return {}
    const counts: Record<string, number> = {}
    for (const ban of data.banned_ips) {
      counts[ban.jail] = (counts[ban.jail] || 0) + 1
    }
    return counts
  }, [data])

  const countryCounts = useMemo(() => {
    if (!data) return {}
    const counts: Record<string, number> = {}
    for (const ban of data.banned_ips) {
      const country = ban.country || 'Unknown'
      counts[country] = (counts[country] || 0) + 1
    }
    return counts
  }, [data])

  const orgCounts = useMemo(() => {
    if (!data) return {}
    const counts: Record<string, number> = {}
    for (const ban of data.banned_ips) {
      const org = ban.org?.replace(/^AS\d+\s*/, '') || 'Unknown'
      counts[org] = (counts[org] || 0) + 1
    }
    return counts
  }, [data])

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
          <StatCard label="Total Banned (all time)" value={data.total_banned} color="text-amber-400" />
          <StatCard label="Jails Active" value={Object.keys(jailCounts).length} color="text-blue-400" />
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

      {/* Sub-tab navigation */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-slate-800 rounded-lg p-0.5 border border-slate-700">
          <button
            onClick={() => setSubTab('bans')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              subTab === 'bans' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <ShieldBan className="w-3.5 h-3.5" /> Bans
          </button>
          <button
            onClick={() => setSubTab('report')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              subTab === 'report' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" /> Report
          </button>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 hover:text-blue-300 hover:bg-slate-700 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh Now'}
        </button>
      </div>

      {/* ── Bans Tab ─────────────────────────────────────────── */}
      {subTab === 'bans' && data && (
        <>
          {pagedBans.length > 0 ? (
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
                  {pagedBans.map((ban, i) => (
                    <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="p-3">
                        <button onClick={() => openDetail(ban.ip)} className="text-left hover:underline">
                          <code className="text-red-400 text-xs font-mono">{ban.ip}</code>
                        </button>
                        {ban.hostname && (
                          <p className="text-xs text-slate-500 truncate max-w-[200px]">{ban.hostname}</p>
                        )}
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1.5">
                          <Globe className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                          <p className="text-slate-200 text-xs">
                            {[ban.city, ban.region, ban.country].filter(Boolean).join(', ') || 'Unknown'}
                          </p>
                        </div>
                      </td>
                      <td className="p-3 text-xs text-slate-400 max-w-[200px] truncate">
                        {ban.org || '—'}
                      </td>
                      <td className="p-3">
                        <JailBadge jail={ban.jail} />
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
                {pagedBans.map((ban, i) => (
                  <div key={i} className="p-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <button onClick={() => openDetail(ban.ip)} className="hover:underline">
                        <code className="text-red-400 text-xs font-mono">{ban.ip}</code>
                      </button>
                      <div className="flex items-center gap-1.5">
                        <JailBadge jail={ban.jail} />
                        <button onClick={() => handleUnban(ban.ip)} className="p-1 text-slate-500 hover:text-amber-400" title="Unban">
                          <Unlock className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="text-xs text-slate-300">
                      {[ban.city, ban.region, ban.country].filter(Boolean).join(', ') || 'Unknown'}
                    </p>
                    {ban.org && <p className="text-xs text-slate-500 truncate">{ban.org}</p>}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 text-center text-slate-500 text-sm">
              {data.last_updated ? 'No banned IPs' : 'Ban monitor has not run yet — data will appear within a minute'}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.banned_ips.length)} of {data.banned_ips.length}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700 disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: totalPages }, (_, i) => (
                  <button
                    key={i}
                    onClick={() => setPage(i)}
                    className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                      i === page ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
                    }`}
                  >
                    {i + 1}
                  </button>
                ))}
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700 disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Report Tab ───────────────────────────────────────── */}
      {subTab === 'report' && data && (
        <div className="space-y-5">
          {/* Ban by Jail */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Bans by Jail Type</h4>
            <div className="space-y-2">
              {Object.entries(jailCounts).sort((a, b) => b[1] - a[1]).map(([jail, count]) => {
                const pct = data.banned_ips.length > 0 ? (count / data.banned_ips.length) * 100 : 0
                return (
                  <div key={jail}>
                    <div className="flex justify-between text-xs mb-1">
                      <JailBadge jail={jail} />
                      <span className="text-slate-300 font-mono">{count}</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div
                        className={`h-full rounded-full transition-all ${
                          jail === 'sshd' ? 'bg-amber-500' : jail === 'nginx-exploit' ? 'bg-red-500' : 'bg-purple-500'
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Ban by Country */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Bans by Country</h4>
            <div className="space-y-2">
              {Object.entries(countryCounts).sort((a, b) => b[1] - a[1]).map(([country, count]) => {
                const pct = data.banned_ips.length > 0 ? (count / data.banned_ips.length) * 100 : 0
                return (
                  <div key={country}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-300 flex items-center gap-1">
                        <Globe className="w-3 h-3 text-slate-500" />
                        {country}
                      </span>
                      <span className="text-slate-400 font-mono">{count} ({pct.toFixed(0)}%)</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div className="h-full rounded-full bg-cyan-500 transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Ban by ISP/Org */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Bans by ISP / Provider</h4>
            <div className="space-y-1.5">
              {Object.entries(orgCounts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([org, count]) => (
                <div key={org} className="flex justify-between text-xs">
                  <span className="text-slate-400 truncate max-w-[250px]">{org}</span>
                  <span className="text-slate-300 font-mono shrink-0 ml-2">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Summary</h4>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-slate-500">Total IPs Banned</p>
                <p className="text-white font-bold text-lg">{data.banned_ips.length}</p>
              </div>
              <div>
                <p className="text-slate-500">Countries</p>
                <p className="text-white font-bold text-lg">{Object.keys(countryCounts).length}</p>
              </div>
              <div>
                <p className="text-slate-500">ISPs</p>
                <p className="text-white font-bold text-lg">{Object.keys(orgCounts).length}</p>
              </div>
              <div>
                <p className="text-slate-500">Ban Duration</p>
                <p className="text-white font-bold text-lg">2 years</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <p className="text-xs text-slate-600">
        All bans are full DROP (all ports, all protocols including ICMP). Auto-detection bans new offenders automatically.
      </p>

      {/* Ban Detail Modal */}
      {detailIp && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setDetailIp(null)}>
          <div
            className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-lg max-h-[85vh] flex flex-col shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-4 border-b border-slate-700 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400" />
                <h3 className="text-sm font-bold text-white">Ban Details: <code className="text-red-400">{detailIp}</code></h3>
              </div>
              <button onClick={() => setDetailIp(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-4">
              {detailLoading && <p className="text-slate-400 text-sm text-center py-4">Loading...</p>}

              {detailData && (
                <>
                  <div className="text-xs text-slate-400">
                    <span className="text-white font-bold text-lg">{detailData.total_hits}</span> total requests logged
                  </div>

                  {/* Categories */}
                  {Object.keys(detailData.categories).length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-slate-300 mb-2">Attack Categories</h4>
                      <div className="space-y-1.5">
                        {Object.entries(detailData.categories).sort((a, b) => b[1] - a[1]).map(([cat, count]) => {
                          const pct = detailData.total_hits > 0 ? (count / detailData.total_hits) * 100 : 0
                          return (
                            <div key={cat}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="text-slate-300">{cat}</span>
                                <span className="text-slate-400 font-mono">{count} ({pct.toFixed(0)}%)</span>
                              </div>
                              <div className="w-full bg-slate-700 rounded-full h-1.5">
                                <div className="h-full rounded-full bg-red-500 transition-all" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Sample requests */}
                  {detailData.sample_requests.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-slate-300 mb-2">
                        Sample Requests ({Math.min(detailData.sample_requests.length, 20)} of {detailData.total_hits})
                      </h4>
                      <div className="space-y-1 max-h-48 overflow-y-auto">
                        {detailData.sample_requests.map((line, i) => (
                          <p key={i} className="text-[10px] text-slate-500 font-mono break-all bg-slate-900/50 rounded px-2 py-1">
                            {line}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailData.total_hits === 0 && (
                    <p className="text-sm text-slate-500 text-center py-4">
                      No log entries found — IP may have been banned via manual action or logs were rotated.
                    </p>
                  )}
                </>
              )}
            </div>

            <div className="p-3 border-t border-slate-700 shrink-0 text-right">
              <button onClick={() => setDetailIp(null)} className="px-4 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
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

const JAIL_COLORS: Record<string, string> = {
  sshd: 'text-amber-400 bg-amber-900/30',
  'nginx-exploit': 'text-red-400 bg-red-900/30',
  'zenithgrid-intrusion': 'text-purple-400 bg-purple-900/30',
}

function JailBadge({ jail }: { jail: string }) {
  const color = JAIL_COLORS[jail] || 'text-slate-400 bg-slate-700/50'
  return <span className={`text-xs px-2 py-0.5 rounded-full ${color}`}>{jail}</span>
}
