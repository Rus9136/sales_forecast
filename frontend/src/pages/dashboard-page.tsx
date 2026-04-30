import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, ChevronRight, RefreshCw } from 'lucide-react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useQueryClient } from '@tanstack/react-query'

import { useDailySales, useSalesHeatmap } from '@/hooks/use-sales'
import { useForecastComparison } from '@/hooks/use-forecast'
import { useWaiterSales } from '@/hooks/use-waiter-sales'
import { useDepartments } from '@/hooks/use-departments'
import { useBonusReportSummary } from '@/hooks/use-bonus'
import { Sparkline } from '@/components/shared/sparkline'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { daysAgo, formatDate, toISODate } from '@/lib/formatters'
import { cn } from '@/lib/utils'

type PeriodKey = '7' | '30' | '90' | '365'
type Granularity = 'day' | 'week' | 'month'

const PERIOD_OPTIONS: { key: PeriodKey; label: string; days: number }[] = [
  { key: '7', label: '7 дней', days: 7 },
  { key: '30', label: '30 дней', days: 30 },
  { key: '90', label: '90 дней', days: 90 },
  { key: '365', label: 'Год', days: 365 },
]

const DOW_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function fmtCompact(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return (value / 1_000_000_000).toFixed(1) + 'B'
  if (abs >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M'
  if (abs >= 1_000) return (value / 1_000).toFixed(1) + 'k'
  return Math.round(value).toString()
}

function fmtKZT(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return Math.round(value).toLocaleString('ru-RU') + ' ₸'
}

function fmtKZTCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return fmtCompact(value) + ' ₸'
}

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}

function isoWeekKey(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  const day = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((+d - +yearStart) / 86400000 + 1) / 7)
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

function monthKey(iso: string): string {
  return iso.slice(0, 7)
}

function bucketKey(iso: string, gran: Granularity): string {
  if (gran === 'week') return isoWeekKey(iso)
  if (gran === 'month') return monthKey(iso)
  return iso
}

function formatBucket(key: string, gran: Granularity): string {
  if (gran === 'day') return shortDate(key)
  if (gran === 'week') {
    const [, w] = key.split('-W')
    return `Нед. ${w}`
  }
  // month: YYYY-MM
  const [y, m] = key.split('-')
  const months = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
  return `${months[Number(m) - 1] ?? m} ${y.slice(2)}`
}

function buildDailyTotals(rows: Array<{ date: string; total_sales: number }>): Map<string, number> {
  const map = new Map<string, number>()
  for (const r of rows) {
    map.set(r.date, (map.get(r.date) ?? 0) + r.total_sales)
  }
  return map
}

export function DashboardPage() {
  const qc = useQueryClient()
  const [period, setPeriod] = useState<PeriodKey>('30')
  const [gran, setGran] = useState<Granularity>('day')

  const config = PERIOD_OPTIONS.find((p) => p.key === period)!

  // Periods: current = [from..to], previous = [prevFrom..prevTo]
  const today = new Date()
  const toDate = toISODate(today)
  const fromDate = daysAgo(config.days - 1)
  const prevToD = new Date(today)
  prevToD.setDate(prevToD.getDate() - config.days)
  const prevTo = toISODate(prevToD)
  const prevFromD = new Date(prevToD)
  prevFromD.setDate(prevFromD.getDate() - (config.days - 1))
  const prevFrom = toISODate(prevFromD)

  // Bonus fund — current month
  const bonusYear = today.getFullYear()
  const bonusMonth = today.getMonth() + 1
  const prevMonthDate = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const prevBonusYear = prevMonthDate.getFullYear()
  const prevBonusMonth = prevMonthDate.getMonth() + 1

  // Queries
  const dailyCur = useDailySales({ from_date: fromDate, to_date: toDate })
  const dailyPrev = useDailySales({ from_date: prevFrom, to_date: prevTo })
  const comparison = useForecastComparison({ from_date: fromDate, to_date: toDate })
  const heatmap = useSalesHeatmap({ from_date: fromDate, to_date: toDate })
  const waiterSales = useWaiterSales({ from_date: fromDate, to_date: toDate })
  const departments = useDepartments(true)
  const bonusCur = useBonusReportSummary({ year: bonusYear, month: bonusMonth })
  const bonusPrev = useBonusReportSummary({ year: prevBonusYear, month: prevBonusMonth })

  const isLoading =
    dailyCur.isLoading ||
    comparison.isLoading ||
    heatmap.isLoading ||
    waiterSales.isLoading

  // ── KPI data ────────────────────────────────────────────────────────────
  const dailyTotalsCur = useMemo(
    () => buildDailyTotals(dailyCur.data ?? []),
    [dailyCur.data],
  )
  const dailyTotalsPrev = useMemo(
    () => buildDailyTotals(dailyPrev.data ?? []),
    [dailyPrev.data],
  )

  const sortedDailyKeys = useMemo(
    () => Array.from(dailyTotalsCur.keys()).sort(),
    [dailyTotalsCur],
  )
  const sortedDailyValues = useMemo(
    () => sortedDailyKeys.map((k) => dailyTotalsCur.get(k) ?? 0),
    [sortedDailyKeys, dailyTotalsCur],
  )

  const totalRevenueCur = sortedDailyValues.reduce((s, v) => s + v, 0)
  const totalRevenuePrev = Array.from(dailyTotalsPrev.values()).reduce((s, v) => s + v, 0)

  const daysWithDataCur = sortedDailyKeys.length || 1
  const daysWithDataPrev = dailyTotalsPrev.size || 1
  const avgPerDayCur = totalRevenueCur / daysWithDataCur
  const avgPerDayPrev = totalRevenuePrev / daysWithDataPrev

  const activeBranchesCur = useMemo(() => {
    const set = new Set<string>()
    for (const r of dailyCur.data ?? []) {
      if (r.total_sales > 0) set.add(r.department_id)
    }
    return set.size
  }, [dailyCur.data])
  const activeBranchesPrev = useMemo(() => {
    const set = new Set<string>()
    for (const r of dailyPrev.data ?? []) {
      if (r.total_sales > 0) set.add(r.department_id)
    }
    return set.size
  }, [dailyPrev.data])

  const bonusFundCur = useMemo(
    () => (bonusCur.data ?? []).reduce((s, r) => s + Number(r.total || 0), 0),
    [bonusCur.data],
  )
  const bonusFundPrev = useMemo(
    () => (bonusPrev.data ?? []).reduce((s, r) => s + Number(r.total || 0), 0),
    [bonusPrev.data],
  )

  const delta = (cur: number, prev: number): number | null => {
    if (!prev) return null
    return ((cur - prev) / prev) * 100
  }

  const sparkSlice = sortedDailyValues.slice(-Math.min(30, sortedDailyValues.length))

  const KPIS = [
    {
      label: `Выручка за ${config.days} ${config.days === 7 ? 'дней' : config.days === 365 ? 'дней' : 'дней'}`,
      value: fmtKZT(totalRevenueCur),
      delta: delta(totalRevenueCur, totalRevenuePrev),
      spark: sparkSlice,
      hint: 'vs пред. период',
    },
    {
      label: 'Среднее за день',
      value: fmtKZT(avgPerDayCur),
      delta: delta(avgPerDayCur, avgPerDayPrev),
      spark: sparkSlice,
      hint: 'vs пред. период',
    },
    {
      label: 'Активных филиалов',
      value: activeBranchesCur.toLocaleString('ru-RU'),
      delta: delta(activeBranchesCur, activeBranchesPrev),
      spark: sparkSlice,
      hint: 'vs пред. период',
    },
    {
      label: 'Бонусный фонд (тек. месяц)',
      value: fmtKZT(bonusFundCur),
      delta: delta(bonusFundCur, bonusFundPrev),
      spark: sparkSlice,
      hint: 'vs пред. месяц',
    },
  ]

  // ── Chart: forecast vs actual aggregated ────────────────────────────────
  const chartData = useMemo(() => {
    const rows = comparison.data ?? []
    const factByBucket = new Map<string, number>()
    const fcByBucket = new Map<string, number>()
    const orderedKeys: string[] = []

    for (const r of rows) {
      const key = bucketKey(r.date, gran)
      if (!factByBucket.has(key)) {
        orderedKeys.push(key)
        factByBucket.set(key, 0)
        fcByBucket.set(key, 0)
      }
      factByBucket.set(key, (factByBucket.get(key) ?? 0) + (r.actual_sales ?? 0))
      if (r.predicted_sales != null) {
        fcByBucket.set(key, (fcByBucket.get(key) ?? 0) + r.predicted_sales)
      }
    }

    orderedKeys.sort()
    return orderedKeys.map((k) => ({
      bucket: k,
      label: formatBucket(k, gran),
      fact: factByBucket.get(k) ?? 0,
      forecast: fcByBucket.get(k) ?? 0,
    }))
  }, [comparison.data, gran])

  // ── Top branches ────────────────────────────────────────────────────────
  const topBranches = useMemo(() => {
    const dept = new Map<string, string>()
    for (const d of departments.data ?? []) {
      dept.set(d.id, d.name)
    }
    const totals = new Map<string, number>()
    for (const r of dailyCur.data ?? []) {
      totals.set(r.department_id, (totals.get(r.department_id) ?? 0) + r.total_sales)
    }
    return Array.from(totals.entries())
      .map(([id, sum]) => ({ id, name: dept.get(id) ?? id.slice(0, 8), sum }))
      .sort((a, b) => b.sum - a.sum)
      .slice(0, 6)
  }, [dailyCur.data, departments.data])
  const topBranchMax = topBranches[0]?.sum ?? 1

  // ── Top waiters ─────────────────────────────────────────────────────────
  const topWaiters = useMemo(() => {
    const dept = new Map<string, string>()
    for (const d of departments.data ?? []) {
      dept.set(d.id, d.name)
    }
    const totals = new Map<string, { name: string; branch: string; sum: number }>()
    for (const r of waiterSales.data ?? []) {
      const key = r.waiter_name
      const prev = totals.get(key)
      const branch = dept.get(r.department_id) ?? ''
      if (prev) {
        prev.sum += r.total_sales
      } else {
        totals.set(key, { name: r.waiter_name, branch, sum: r.total_sales })
      }
    }
    return Array.from(totals.values())
      .sort((a, b) => b.sum - a.sum)
      .slice(0, 6)
  }, [waiterSales.data, departments.data])
  const topWaiterMax = topWaiters[0]?.sum ?? 1

  // ── Heatmap ────────────────────────────────────────────────────────────
  const heatGrid = heatmap.data?.grid ?? []
  const heatMax = useMemo(() => {
    let m = 0
    for (const row of heatGrid) for (const v of row) if (v > m) m = v
    return m || 1
  }, [heatGrid])
  const heatColor = (v: number): string => {
    const t = Math.max(0, Math.min(1, v / heatMax))
    return `oklch(${(0.96 - t * 0.34).toFixed(3)} ${(0.02 + t * 0.13).toFixed(3)} 162)`
  }

  const handleRefresh = () => {
    void qc.invalidateQueries({ queryKey: ['sales'] })
    void qc.invalidateQueries({ queryKey: ['forecast'] })
    void qc.invalidateQueries({ queryKey: ['bonus'] })
    void qc.invalidateQueries({ queryKey: ['departments'] })
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Дашборд</h1>
          <span className="sub">
            Период: {formatDate(fromDate)} — {formatDate(toDate)} · Все подразделения
          </span>
        </div>
        <div className="page__actions">
          <div className="seg">
            {PERIOD_OPTIONS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={cn(period === p.key && 'active')}
                onClick={() => setPeriod(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn--primary" onClick={handleRefresh}>
            <RefreshCw size={14} /> Обновить
          </button>
        </div>
      </div>

      {isLoading && !dailyCur.data ? (
        <LoadingSpinner />
      ) : (
        <div className="dash">
          {/* === KPI row === */}
          <div className="kpi-row">
            {KPIS.map((k, i) => (
              <div key={i} className="kpi">
                <div className="kpi__label">{k.label}</div>
                <div className="kpi__value">{k.value}</div>
                <div className="kpi__foot">
                  {k.delta != null ? (
                    <span className={cn('trend', k.delta >= 0 ? 'trend--pos' : 'trend--neg')}>
                      {k.delta >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                      {fmtPctSigned(k.delta)}
                    </span>
                  ) : (
                    <span className="trend">—</span>
                  )}
                  <span style={{ fontSize: 11 }}>{k.hint}</span>
                </div>
                <div className="kpi__spark">
                  <Sparkline data={k.spark} width={120} height={32} />
                </div>
              </div>
            ))}
          </div>

          {/* === Row 2: forecast chart + top branches === */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Динамика продаж — факт и прогноз</div>
                  <div className="card__sub">Сравнение с прогнозируемой моделью</div>
                </div>
                <div className="seg">
                  {(['day', 'week', 'month'] as const).map((g) => (
                    <button
                      key={g}
                      type="button"
                      className={cn(gran === g && 'active')}
                      onClick={() => setGran(g)}
                    >
                      {g === 'day' ? 'День' : g === 'week' ? 'Неделя' : 'Месяц'}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ padding: '10px 14px 14px', height: 320 }}>
                {chartData.length === 0 ? (
                  <EmptyState text="Нет данных за выбранный период" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData}>
                      <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                        stroke="var(--chart-axis)"
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                        stroke="var(--chart-axis)"
                        tickFormatter={(v) => fmtCompact(Number(v))}
                      />
                      <Tooltip
                        formatter={(value, name) => [fmtKZT(Number(value)), name as string]}
                        labelFormatter={(l) => String(l)}
                        contentStyle={{
                          background: 'var(--surface)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          fontSize: 12,
                          color: 'var(--text)',
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Area
                        type="monotone"
                        dataKey="fact"
                        name="Факт"
                        stroke="var(--accent)"
                        fill="var(--accent)"
                        fillOpacity={0.18}
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="forecast"
                        name="Прогноз"
                        stroke="var(--text-subtle)"
                        strokeWidth={1.5}
                        strokeDasharray="4 4"
                        dot={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Топ филиалов</div>
                  <div className="card__sub">По выручке за период</div>
                </div>
                <Link to="/forecast/branches" className="btn btn--ghost btn--sm">
                  Все <ChevronRight size={11} />
                </Link>
              </div>
              {topBranches.length === 0 ? (
                <EmptyState text="Нет данных" />
              ) : (
                <div className="top-list">
                  {topBranches.map((b, i) => (
                    <div key={b.id} className="top-row">
                      <span className="rank">{String(i + 1).padStart(2, '0')}</span>
                      <span className="nm" title={b.name}>{b.name}</span>
                      <span className="bar">
                        <i style={{ width: `${(b.sum / topBranchMax) * 100}%` }} />
                      </span>
                      <span className="val">{fmtKZTCompact(b.sum)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* === Row 3: heatmap + top waiters === */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Heatmap — продажи по часам и дням недели</div>
                  <div className="card__sub">Пиковые периоды активности</div>
                </div>
                <div className="heatmap-legend">
                  <span>меньше</span>
                  <span className="scale">
                    {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t, i) => (
                      <i
                        key={i}
                        style={{
                          background: `oklch(${0.96 - t * 0.34} ${0.02 + t * 0.13} 162)`,
                        }}
                      />
                    ))}
                  </span>
                  <span>больше</span>
                </div>
              </div>
              <div style={{ padding: 16 }}>
                <div className="heatmap" style={{ marginBottom: 4 }}>
                  <span />
                  {Array.from({ length: 24 }).map((_, h) => (
                    <span key={h} className="h-col">
                      {h % 3 === 0 ? `${h}` : ''}
                    </span>
                  ))}
                </div>
                {heatGrid.length === 0 ? (
                  <EmptyState text="Нет данных" />
                ) : (
                  heatGrid.map((row, di) => (
                    <div key={di} className="heatmap" style={{ marginBottom: 3 }}>
                      <span className="h-row-label">{DOW_LABELS[di]}</span>
                      {row.map((v, h) => (
                        <div
                          key={h}
                          className="h-cell"
                          style={{ background: heatColor(v) }}
                          title={`${DOW_LABELS[di]} ${h}:00 — ${fmtKZT(v)}`}
                        />
                      ))}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Топ официантов</div>
                  <div className="card__sub">По выручке за период</div>
                </div>
                <Link to="/sales/waiters" className="btn btn--ghost btn--sm">
                  Все <ChevronRight size={11} />
                </Link>
              </div>
              {topWaiters.length === 0 ? (
                <EmptyState text="Нет данных" />
              ) : (
                <div className="top-list">
                  {topWaiters.map((w, i) => (
                    <div key={w.name} className="top-row">
                      <span className="rank">{String(i + 1).padStart(2, '0')}</span>
                      <span className="nm" title={w.name}>
                        {w.name}
                        {w.branch && <div className="sub">{w.branch}</div>}
                      </span>
                      <span className="bar">
                        <i style={{ width: `${(w.sum / topWaiterMax) * 100}%` }} />
                      </span>
                      <span className="val">{fmtKZTCompact(w.sum)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
