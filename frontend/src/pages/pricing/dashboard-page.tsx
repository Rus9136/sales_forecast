import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, RefreshCw } from 'lucide-react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useQueryClient } from '@tanstack/react-query'

import { useDepartmentWeekly, useRecommendationsSummary } from '@/hooks/use-pricing'
import { DepartmentSelect } from '@/components/shared/department-select'
import { Sparkline } from '@/components/shared/sparkline'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { formatCurrency, toISODate } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type { DepartmentWeekly } from '@/types/pricing'

const ALL = '__all__'

type PeriodKey = '8' | '12' | '26' | '52'
const PERIOD_OPTIONS: { key: PeriodKey; label: string; weeks: number }[] = [
  { key: '8', label: '8 нед.', weeks: 8 },
  { key: '12', label: '12 нед.', weeks: 12 },
  { key: '26', label: '26 нед.', weeks: 26 },
  { key: '52', label: 'Год', weeks: 52 },
]

type Metric = 'gp' | 'revenue' | 'margin' | 'aov'
const METRIC_OPTIONS: { key: Metric; label: string }[] = [
  { key: 'gp', label: 'Прибыль' },
  { key: 'revenue', label: 'Выручка' },
  { key: 'margin', label: 'Маржа' },
  { key: 'aov', label: 'Средний чек' },
]

interface WeekAgg {
  week: string
  revenue: number
  cost: number
  gp: number
  receipts: number
  guests: number
  covWeighted: number
  covRevenue: number
}

function fmtCompact(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return (value / 1_000_000_000).toFixed(1) + 'B'
  if (abs >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M'
  if (abs >= 1_000) return (value / 1_000).toFixed(1) + 'k'
  return Math.round(value).toString()
}

function fmtPctSigned(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function fmtRatioPct(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return (value * 100).toFixed(1) + '%'
}

function weekLabel(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}

function aggregateWeeks(rows: DepartmentWeekly[]): WeekAgg[] {
  const map = new Map<string, WeekAgg>()
  for (const r of rows) {
    let w = map.get(r.week_start)
    if (!w) {
      w = {
        week: r.week_start,
        revenue: 0, cost: 0, gp: 0, receipts: 0, guests: 0,
        covWeighted: 0, covRevenue: 0,
      }
      map.set(r.week_start, w)
    }
    w.revenue += r.total_revenue
    w.cost += r.total_cost
    w.gp += r.gross_profit
    w.receipts += r.total_receipts
    w.guests += r.unique_guests
    if (r.cost_coverage != null) {
      w.covWeighted += r.cost_coverage * r.total_revenue
      w.covRevenue += r.total_revenue
    }
  }
  return Array.from(map.values()).sort((a, b) => a.week.localeCompare(b.week))
}

function metricValue(w: WeekAgg, metric: Metric): number {
  switch (metric) {
    case 'gp': return w.gp
    case 'revenue': return w.revenue
    case 'margin': return w.revenue > 0 ? w.gp / w.revenue : 0
    case 'aov': return w.receipts > 0 ? w.revenue / w.receipts : 0
  }
}

export function PricingDashboardPage() {
  const qc = useQueryClient()
  const [deptId, setDeptId] = useState<string>(ALL)
  const [period, setPeriod] = useState<PeriodKey>('12')
  const [metric, setMetric] = useState<Metric>('gp')

  const config = PERIOD_OPTIONS.find((p) => p.key === period)!
  const effectiveDept = deptId === ALL ? undefined : deptId

  // Fetch 2× the period so we can compare current vs previous block of weeks.
  const fromWeek = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - config.weeks * 2 * 7)
    return toISODate(d)
  }, [config.weeks])

  const weekly = useDepartmentWeekly({ department_id: effectiveDept, from_week: fromWeek })
  const recSummary = useRecommendationsSummary(effectiveDept)

  const allWeeks = useMemo(
    () => aggregateWeeks(weekly.data?.items ?? []),
    [weekly.data],
  )

  const { current, previous } = useMemo(() => {
    const n = config.weeks
    const cur = allWeeks.slice(-n)
    const prev = allWeeks.slice(-2 * n, -n)
    return { current: cur, previous: prev }
  }, [allWeeks, config.weeks])

  const sumBlock = (weeks: WeekAgg[]) =>
    weeks.reduce(
      (acc, w) => {
        acc.revenue += w.revenue
        acc.cost += w.cost
        acc.gp += w.gp
        acc.receipts += w.receipts
        acc.covWeighted += w.covWeighted
        acc.covRevenue += w.covRevenue
        return acc
      },
      { revenue: 0, cost: 0, gp: 0, receipts: 0, covWeighted: 0, covRevenue: 0 },
    )

  const cur = sumBlock(current)
  const prev = sumBlock(previous)

  const marginCur = cur.revenue > 0 ? cur.gp / cur.revenue : null
  const marginPrev = prev.revenue > 0 ? prev.gp / prev.revenue : null
  const aovCur = cur.receipts > 0 ? cur.revenue / cur.receipts : null
  const aovPrev = prev.receipts > 0 ? prev.revenue / prev.receipts : null
  const coverageCur = cur.covRevenue > 0 ? cur.covWeighted / cur.covRevenue : null

  const relDelta = (a: number | null, b: number | null): number | null => {
    if (a == null || b == null || !b) return null
    return ((a - b) / b) * 100
  }

  const sparkGp = current.map((w) => w.gp)
  const sparkMargin = current.map((w) => (w.revenue > 0 ? w.gp / w.revenue : 0))
  const sparkAov = current.map((w) => (w.receipts > 0 ? w.revenue / w.receipts : 0))

  const byStatus = recSummary.data?.by_status ?? {}
  const managedCount = byStatus.approved ?? 0
  const newCount = byStatus.new ?? 0
  const potentialGp = recSummary.data?.total_delta_gp_new ?? null

  const KPIS: {
    label: string
    value: string
    delta: number | null
    deltaSuffix?: string
    spark: number[]
    hint: string
  }[] = [
    {
      label: 'Валовая прибыль (GP)',
      value: formatCurrency(cur.gp),
      delta: relDelta(cur.gp, prev.gp),
      spark: sparkGp,
      hint: 'vs пред. период',
    },
    {
      label: 'Маржа GP',
      value: fmtRatioPct(marginCur),
      // delta in percentage points for a ratio metric
      delta:
        marginCur != null && marginPrev != null
          ? (marginCur - marginPrev) * 100
          : null,
      deltaSuffix: ' п.п.',
      spark: sparkMargin,
      hint: 'vs пред. период',
    },
    {
      label: 'Средний чек (AOV)',
      value: formatCurrency(aovCur),
      delta: relDelta(aovCur, aovPrev),
      spark: sparkAov,
      hint: 'vs пред. период',
    },
    {
      label: 'Позиций под управлением',
      value: managedCount.toLocaleString('ru-RU'),
      delta: null,
      spark: [] as number[],
      hint: newCount > 0 ? `${newCount.toLocaleString('ru-RU')} новых на проверке` : 'нет новых',
    },
  ]

  const chartData = useMemo(
    () =>
      current.map((w) => ({
        week: w.week,
        label: weekLabel(w.week),
        value: metricValue(w, metric),
      })),
    [current, metric],
  )

  const isCurrency = metric === 'gp' || metric === 'revenue' || metric === 'aov'
  const tooltipFmt = (v: number) => (isCurrency ? formatCurrency(v) : fmtRatioPct(v))
  const axisFmt = (v: number) => (isCurrency ? fmtCompact(v) : (v * 100).toFixed(0) + '%')

  // Top departments by GP over the current period.
  const topDepts = useMemo(() => {
    const rows = weekly.data?.items ?? []
    const curWeeks = new Set(current.map((w) => w.week))
    const totals = new Map<string, { name: string; gp: number }>()
    for (const r of rows) {
      if (!curWeeks.has(r.week_start)) continue
      const prevRow = totals.get(r.department_id)
      const name = r.department_name ?? r.department_id.slice(0, 8)
      if (prevRow) prevRow.gp += r.gross_profit
      else totals.set(r.department_id, { name, gp: r.gross_profit })
    }
    return Array.from(totals.values())
      .sort((a, b) => b.gp - a.gp)
      .slice(0, 8)
  }, [weekly.data, current])
  const topDeptMax = topDepts[0]?.gp ?? 1

  const handleRefresh = () => {
    void qc.invalidateQueries({ queryKey: ['pricing'] })
  }

  const isLoading = weekly.isLoading && !weekly.data

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Дашборд ценообразования</h1>
          <span className="sub">
            {deptId === ALL ? 'Все подразделения' : 'Подразделение'} · последние {config.weeks} недель
          </span>
        </div>
        <div className="page__actions">
          <DepartmentSelect value={deptId} onChange={setDeptId} includeInactive />
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

      {isLoading ? (
        <LoadingSpinner />
      ) : allWeeks.length === 0 ? (
        <EmptyState text="Нет недельных агрегатов за выбранный период. Запустите агрегацию витрин (A2)." />
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
                      {fmtPctSigned(k.delta)}{k.deltaSuffix ?? ''}
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

          {/* === Row 2: dynamics chart + recommendations summary === */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Динамика по неделям</div>
                  <div className="card__sub">Понедельные агрегаты витрин</div>
                </div>
                <div className="seg">
                  {METRIC_OPTIONS.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      className={cn(metric === m.key && 'active')}
                      onClick={() => setMetric(m.key)}
                    >
                      {m.label}
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
                        tickFormatter={(v) => axisFmt(Number(v))}
                        width={48}
                      />
                      <Tooltip
                        formatter={(value) => [tooltipFmt(Number(value)), METRIC_OPTIONS.find((m) => m.key === metric)?.label ?? '']}
                        labelFormatter={(l) => `Неделя ${l}`}
                        contentStyle={{
                          background: 'var(--surface)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          fontSize: 12,
                          color: 'var(--text)',
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke="var(--accent)"
                        fill="var(--accent)"
                        fillOpacity={0.18}
                        strokeWidth={2}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Рекомендации цен</div>
                  <div className="card__sub">Потенциал и статусы</div>
                </div>
              </div>
              <div style={{ padding: '14px 16px' }}>
                <div className="kpi__label">Потенциал ΔGP (новые)</div>
                <div className="kpi__value" style={{ marginBottom: 14 }}>
                  {potentialGp != null ? formatCurrency(potentialGp) : '—'}
                </div>
                <div className="top-list">
                  {[
                    { key: 'new', label: 'Новые' },
                    { key: 'approved', label: 'Утверждено' },
                    { key: 'rejected', label: 'Отклонено' },
                    { key: 'expired', label: 'Истекло' },
                  ].map((s) => (
                    <div key={s.key} className="top-row">
                      <span className="nm">{s.label}</span>
                      <span className="val">
                        {(byStatus[s.key as keyof typeof byStatus] ?? 0).toLocaleString('ru-RU')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* === Row 3: top departments by GP + data quality === */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Топ подразделений по прибыли</div>
                  <div className="card__sub">GP за период</div>
                </div>
              </div>
              {topDepts.length === 0 ? (
                <EmptyState text="Нет данных" />
              ) : (
                <div className="top-list">
                  {topDepts.map((b, i) => (
                    <div key={b.name + i} className="top-row">
                      <span className="rank">{String(i + 1).padStart(2, '0')}</span>
                      <span className="nm" title={b.name}>{b.name}</span>
                      <span className="bar">
                        <i style={{ width: `${(b.gp / topDeptMax) * 100}%` }} />
                      </span>
                      <span className="val">{fmtCompact(b.gp)} ₸</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Качество данных</div>
                  <div className="card__sub">Покрытие себестоимости</div>
                </div>
              </div>
              <div style={{ padding: '14px 16px' }}>
                <div className="kpi__label">Покрытие COGS (взвеш. по выручке)</div>
                <div className="kpi__value">{fmtRatioPct(coverageCur)}</div>
                <div className="kpi__foot" style={{ marginTop: 8 }}>
                  <span style={{ fontSize: 11 }}>
                    {coverageCur != null && coverageCur < 0.8
                      ? 'Низкое покрытие — GP-метрики могут быть занижены'
                      : 'Достаточно для расчёта маржи'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
