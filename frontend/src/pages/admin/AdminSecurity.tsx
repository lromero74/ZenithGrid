/**
 * Admin Security Tab
 *
 * Displays fail2ban banned IPs with geolocation data, pagination,
 * and visual reports (ban type breakdown, country distribution).
 */

import { useState, useEffect, useMemo } from 'react'
import { ShieldBan, RefreshCw, Globe, Clock, Unlock, ChevronLeft, ChevronRight, BarChart3, PieChart as PieChartIcon, X, AlertTriangle, Search, ChevronsUpDown, ChevronUp, ChevronDown, Layers } from 'lucide-react'
import { adminApi, type BanSnapshot } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

const PAGE_SIZE = 10

type SubTab = 'bans' | 'report'
type ChartMode = 'bar' | 'pie'
type SortField = 'ip' | 'country' | 'org' | 'jail'
type SortDir = 'asc' | 'desc'
type GroupBy = 'none' | 'country' | 'org' | 'jail'

export function AdminSecurity() {
  const [data, setData] = useState<BanSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [subTab, setSubTab] = useState<SubTab>('bans')
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('ip')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [groupBy, setGroupBy] = useState<GroupBy>('none')
  const [chartMode, setChartMode] = useState<ChartMode>('bar')
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

  // Filtered + sorted list (pre-pagination)
  const filteredBans = useMemo(() => {
    if (!data) return []
    const q = search.trim().toLowerCase()
    let list = q
      ? data.banned_ips.filter(b =>
          b.ip.includes(q) ||
          (b.country || '').toLowerCase().includes(q) ||
          (b.org || '').toLowerCase().includes(q) ||
          (b.jail || '').toLowerCase().includes(q) ||
          (b.city || '').toLowerCase().includes(q) ||
          (b.hostname || '').toLowerCase().includes(q)
        )
      : [...data.banned_ips]

    list.sort((a, b) => {
      let av = '', bv = ''
      if (sortField === 'ip') { av = a.ip; bv = b.ip }
      else if (sortField === 'country') { av = a.country || ''; bv = b.country || '' }
      else if (sortField === 'org') { av = a.org || ''; bv = b.org || '' }
      else if (sortField === 'jail') { av = a.jail; bv = b.jail }
      const cmp = av.localeCompare(bv)
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [data, search, sortField, sortDir])

  const handleSort = (field: SortField) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('asc') }
    setPage(0)
  }

  // Reset page when search/sort/group changes
  const handleSearch = (v: string) => { setSearch(v); setPage(0) }
  const handleGroupBy = (v: GroupBy) => { setGroupBy(v); setPage(0) }

  // Pagination (over filtered list)
  const totalPages = Math.ceil(filteredBans.length / PAGE_SIZE)
  const pagedBans = useMemo(() => {
    const start = page * PAGE_SIZE
    return filteredBans.slice(start, start + PAGE_SIZE)
  }, [filteredBans, page])

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
          {/* Search + Group toolbar */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={e => handleSearch(e.target.value)}
                placeholder="Search IP, country, org, jail…"
                className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {search && (
                <button onClick={() => handleSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Layers className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Group:</span>
              {(['none', 'country', 'org', 'jail'] as GroupBy[]).map(g => (
                <button
                  key={g}
                  onClick={() => handleGroupBy(g)}
                  className={`px-2 py-1 rounded transition-colors ${groupBy === g ? 'bg-blue-600 text-white' : 'bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700'}`}
                >
                  {g === 'none' ? 'None' : g === 'country' ? 'Country' : g === 'org' ? 'ISP' : 'Jail'}
                </button>
              ))}
            </div>
            {search && (
              <span className="text-xs text-slate-500">{filteredBans.length} of {data.banned_ips.length}</span>
            )}
          </div>

          {pagedBans.length > 0 ? (
            <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
              {/* Desktop table */}
              <table className="w-full text-sm hidden sm:table">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    {([['ip', 'IP Address'], ['country', 'Location'], ['org', 'ISP / Org'], ['jail', 'Jail']] as [SortField, string][]).map(([field, label]) => (
                      <th key={field} className="text-left p-3">
                        <button onClick={() => handleSort(field)} className="flex items-center gap-1 hover:text-white transition-colors">
                          {label}
                          {sortField === field
                            ? (sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)
                            : <ChevronsUpDown className="w-3 h-3 opacity-40" />}
                        </button>
                      </th>
                    ))}
                    <th className="text-right p-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedBans.map((ban, i) => {
                    const getKey = (b: typeof ban) =>
                      groupBy === 'country' ? (b.country || 'Unknown')
                      : groupBy === 'org' ? (b.org?.replace(/^AS\d+\s*/, '') || 'Unknown')
                      : groupBy === 'jail' ? b.jail
                      : null
                    const groupKey = getKey(ban)
                    const prevBan = pagedBans[i - 1]
                    const prevKey = prevBan ? getKey(prevBan) : null
                    const showHeader = groupKey !== null && groupKey !== prevKey
                    const groupCount = groupKey !== null
                      ? filteredBans.filter(b => getKey(b) === groupKey).length
                      : 0
                    return <>
                      {showHeader && (
                        <tr key={`g-${groupKey}`} className="bg-slate-700/40">
                          <td colSpan={5} className="px-3 py-1.5 text-xs font-semibold text-slate-300 flex items-center gap-2">
                            {groupKey}
                            <span className="text-slate-500 font-normal">({groupCount})</span>
                          </td>
                        </tr>
                      )}
                      <tr key={ban.ip} className="border-b border-slate-700/50 hover:bg-slate-700/30">
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
                    </>
                  })}
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
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filteredBans.length)} of {filteredBans.length}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700 disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {(() => {
                  // Windowed pagination: first, last, current±2, with … gaps
                  const slots: (number | '…')[] = []
                  const add = (n: number) => { if (!slots.includes(n)) slots.push(n) }
                  add(0); add(totalPages - 1)
                  for (let i = Math.max(0, page - 2); i <= Math.min(totalPages - 1, page + 2); i++) add(i)
                  slots.sort((a, b) => (a as number) - (b as number))
                  const withEllipsis: (number | '…')[] = []
                  slots.forEach((s, idx) => {
                    if (idx > 0 && (s as number) - (slots[idx - 1] as number) > 1) withEllipsis.push('…')
                    withEllipsis.push(s)
                  })
                  return withEllipsis.map((s, idx) =>
                    s === '…'
                      ? <span key={`e${idx}`} className="w-7 h-7 flex items-center justify-center text-xs text-slate-500">…</span>
                      : <button
                          key={s}
                          onClick={() => setPage(s as number)}
                          className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                            s === page ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
                          }`}
                        >{(s as number) + 1}</button>
                  )
                })()}
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
          {/* Chart mode toggle */}
          <div className="flex justify-end">
            <div className="flex gap-0.5 bg-slate-800 rounded-lg p-0.5 border border-slate-700">
              <button
                onClick={() => setChartMode('bar')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  chartMode === 'bar' ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
                title="Bar charts"
              >
                <BarChart3 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setChartMode('pie')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  chartMode === 'pie' ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
                title="Pie charts"
              >
                <PieChartIcon className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Ban by Jail */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Bans by Jail Type</h4>
            {chartMode === 'bar' ? (
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
            ) : (
              <PieChart
                data={Object.entries(jailCounts).sort((a, b) => b[1] - a[1])}
                total={data.banned_ips.length}
                colors={Object.fromEntries(
                  Object.entries(jailCounts).map(([jail]) => [
                    jail,
                    jail === 'sshd' ? '#f59e0b' : jail === 'nginx-exploit' ? '#ef4444'
                      : jail === 'nginx-bad-request' ? '#3b82f6' : '#a855f7',
                  ])
                )}
                renderLabel={(label) => <JailBadge jail={label} />}
              />
            )}
          </div>

          {/* Ban by Country */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Bans by Country</h4>
            {chartMode === 'bar' ? (
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
            ) : (
              <PieChart
                data={Object.entries(countryCounts).sort((a, b) => b[1] - a[1])}
                total={data.banned_ips.length}
              />
            )}
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

const PIE_PALETTE = [
  '#ef4444', '#f59e0b', '#a855f7', '#3b82f6', '#06b6d4', '#22c55e',
  '#ec4899', '#f97316', '#8b5cf6', '#14b8a6', '#eab308', '#64748b',
]

function PieChart({
  data,
  total,
  colors,
  renderLabel,
}: {
  data: [string, number][]
  total: number
  colors?: Record<string, string>
  renderLabel?: (label: string) => React.ReactNode
}) {
  if (total === 0) return <p className="text-xs text-slate-500 text-center py-4">No data</p>

  const size = 140
  const cx = size / 2
  const cy = size / 2
  const r = 55
  let cumulative = 0

  const slices = data.map(([label, count], i) => {
    const pct = count / total
    const startAngle = cumulative * 2 * Math.PI - Math.PI / 2
    cumulative += pct
    const endAngle = cumulative * 2 * Math.PI - Math.PI / 2
    const large = pct > 0.5 ? 1 : 0
    const x1 = cx + r * Math.cos(startAngle)
    const y1 = cy + r * Math.sin(startAngle)
    const x2 = cx + r * Math.cos(endAngle)
    const y2 = cy + r * Math.sin(endAngle)
    const fill = colors?.[label] || PIE_PALETTE[i % PIE_PALETTE.length]

    // For a single 100% slice, draw a full circle
    if (pct >= 0.9999) {
      return (
        <circle key={label} cx={cx} cy={cy} r={r} fill={fill} />
      )
    }

    return (
      <path
        key={label}
        d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`}
        fill={fill}
        stroke="#1e293b"
        strokeWidth="1"
      />
    )
  })

  return (
    <div className="flex flex-col sm:flex-row items-center gap-4">
      <svg width={size} height={size} className="shrink-0">
        {slices}
      </svg>
      <div className="space-y-1.5 min-w-0">
        {data.map(([label, count], i) => {
          const pct = ((count / total) * 100).toFixed(0)
          const fill = colors?.[label] || PIE_PALETTE[i % PIE_PALETTE.length]
          return (
            <div key={label} className="flex items-center gap-2 text-xs">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: fill }} />
              <span className="text-slate-300 truncate">
                {renderLabel ? renderLabel(label) : label}
              </span>
              <span className="text-slate-500 font-mono ml-auto shrink-0">{count} ({pct}%)</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
