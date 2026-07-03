import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, Download, RefreshCw, X } from 'lucide-react'
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

import {
  useDepartmentWeekly,
  useOutcomesSummary,
  usePricingReports,
  useRecommendationsSummary,
} from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { useAuth } from '@/contexts/auth-context'
import { Sparkline } from '@/components/shared/sparkline'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { Term, GLOSSARY } from '@/components/shared/term'
import { apiDownload } from '@/lib/api-client'
import { formatCurrency, formatDate, toISODate } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type { DepartmentWeekly } from '@/types/pricing'

const ONBOARDING_KEY = 'sf.pricing.onboarding.dismissed'

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
  if (abs >= 1_000_000_000) return (value / 1_000_000_000).toFixed(1) + ' млрд'
  if (abs >= 1_000_000) return (value / 1_000_000).toFixed(1) + ' млн'
  if (abs >= 1_000) return (value / 1_000).toFixed(0) + ' тыс'
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
  const { hasSection } = useAuth()
  const { effectiveDepartmentId } = usePricingScope()

  const [period, setPeriod] = useState<PeriodKey>('12')
  const [metric, setMetric] = useState<Metric>('gp')
  const [onboardingHidden, setOnboardingHidden] = useState(
    () => {
      try { return localStorage.getItem(ONBOARDING_KEY) === '1' } catch { return true }
    },
  )

  const config = PERIOD_OPTIONS.find((p) => p.key === period)!

  // Fetch 2× the period so we can compare current vs previous block of weeks.
  const fromWeek = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - config.weeks * 2 * 7)
    return toISODate(d)
  }, [config.weeks])

  const weekly = useDepartmentWeekly({ department_id: effectiveDepartmentId, from_week: fromWeek })
  const recSummary = useRecommendationsSummary(effectiveDepartmentId)
  const outcomes = useOutcomesSummary(effectiveDepartmentId)
  const canReports = hasSection('pricing.reports')
  const reports = usePricingReports(canReports ? { department_id: effectiveDepartmentId } : {})

  const dismissOnboarding = () => {
    setOnboardingHidden(true)
    try { localStorage.setItem(ONBOARDING_KEY, '1') } catch { /* noop */ }
  }

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

  const byStatus = recSummary.data?.by_status ?? {}
  const newCount = byStatus.new ?? 0
  const approvedCount = byStatus.approved ?? 0
  const appliedCount = byStatus.applied ?? 0
  const evaluatedCount = outcomes.data?.total_evaluated ?? 0
  const potentialGp = recSummary.data?.total_delta_gp_new ?? null

  const latestReport = useMemo(() => {
    const items = reports.data?.items ?? []
    return items.length > 0 ? items[0] : null
  }, [reports.data])

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
    const totals = new Map<string, { id: string; name: string; gp: number }>()
    for (const r of rows) {
      if (!curWeeks.has(r.week_start)) continue
      const prevRow = totals.get(r.department_id)
      const name = r.department_name ?? r.department_id.slice(0, 8)
      if (prevRow) prevRow.gp += r.gross_profit
      else totals.set(r.department_id, { id: r.department_id, name, gp: r.gross_profit })
    }
    return Array.from(totals.values())
      .sort((a, b) => b.gp - a.gp)
      .slice(0, 8)
  }, [weekly.data, current])
  const topDeptMax = topDepts[0]?.gp ?? 1

  const handleRefresh = () => {
    void qc.invalidateQueries({ queryKey: ['pricing'] })
  }

  const handleExportApproved = async () => {
    try {
      const params = new URLSearchParams({ status: 'approved' })
      if (effectiveDepartmentId) params.set('department_id', effectiveDepartmentId)
      const blob = await apiDownload(`/api/pricing-engine/recommendations/export?${params}`)
      const href = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = href
      a.download = 'approved_prices.xlsx'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(href)
    } catch {
      /* ошибку скачивания покажет браузер */
    }
  }

  const outcomeActual = outcomes.data?.actual_delta_gp ?? null
  const outcomeExpected = outcomes.data?.expected_delta_gp ?? null

  const sparkGp = current.map((w) => w.gp)
  const sparkMargin = current.map((w) => (w.revenue > 0 ? w.gp / w.revenue : 0))
  const sparkAov = current.map((w) => (w.receipts > 0 ? w.revenue / w.receipts : 0))

  const isLoading = weekly.isLoading && !weekly.data

  return (
    <>
      {/* Онбординг: цикл работы в одну строку */}
      {!onboardingHidden && (
        <div className="pricing-onb">
          <span className="ic">?</span>
          <p>
            <b>Как это работает.</b> Каждую ночь система предлагает изменения цен → вы
            утверждаете их во вкладке «Рекомендации» → выгружаете XLSX и загружаете в iiko →
            система сама замечает применение и через 14 дней показывает фактический эффект
            в «Результатах».
          </p>
          <button type="button" className="close" onClick={dismissOnboarding} title="Скрыть">
            <X size={14} />
          </button>
        </div>
      )}

      {/* «Сделать сегодня» */}
      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Сделать сегодня</div>
            <div className="card__sub">Что требует вашего участия прямо сейчас</div>
          </div>
          <button type="button" className="btn" onClick={handleRefresh}>
            <RefreshCw size={14} /> Обновить
          </button>
        </div>
        <div style={{ padding: '12px 16px 16px' }}>
          <div className="pricing-today">
            <Link
              to="/pricing/recommendations?status=new"
              className={cn('pricing-today__item', newCount > 0 && 'hot')}
            >
              <span className="tt">
                {newCount > 0
                  ? `${newCount.toLocaleString('ru-RU')} новых предложений`
                  : 'Новых предложений нет'}
                {potentialGp != null && potentialGp > 0 && (
                  <span style={{ color: 'var(--pos)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    +{fmtCompact(potentialGp)} ₸/нед
                  </span>
                )}
              </span>
              <span className="ds">
                {newCount > 0
                  ? 'Система рассчитала выгодные изменения цен — просмотрите и утвердите.'
                  : 'Следующий пересчёт — сегодня ночью в 05:00.'}
              </span>
              {newCount > 0 && <span className="cta">Разобрать →</span>}
            </Link>

            <div className="pricing-today__item" style={{ cursor: approvedCount > 0 ? 'pointer' : 'default' }}>
              <span className="tt">
                {approvedCount > 0
                  ? `${approvedCount.toLocaleString('ru-RU')} цен ждут загрузки в iiko`
                  : 'Все утверждённые цены загружены'}
              </span>
              <span className="ds">
                {approvedCount > 0
                  ? 'Утверждены, но ещё не появились в каталоге. Через 30 дней истекут.'
                  : 'Утверждайте новые предложения — они появятся здесь для выгрузки.'}
              </span>
              {approvedCount > 0 && (
                <button
                  type="button"
                  className="cta"
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', font: 'inherit', color: 'var(--accent)', fontWeight: 650, fontSize: 12 }}
                  onClick={handleExportApproved}
                >
                  <Download size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> Скачать XLSX →
                </button>
              )}
            </div>

            {canReports ? (
              <Link to="/pricing/reports" className="pricing-today__item">
                <span className="tt">
                  {latestReport ? 'Готов свежий отчёт' : 'Отчётов пока нет'}
                </span>
                <span className="ds">
                  {latestReport
                    ? `ИИ-сводка за ${formatDate(latestReport.period_start)} – ${formatDate(latestReport.period_end)}: что сработало, что нет.`
                    : 'Еженедельная ИИ-сводка появится в понедельник утром (08:00).'}
                </span>
                {latestReport && <span className="cta">Открыть →</span>}
              </Link>
            ) : (
              <div className="pricing-today__item">
                <span className="tt">Эффект измеряется автоматически</span>
                <span className="ds">Через 14 дней после применения цены — факт против ожидания.</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Воронка цикла */}
      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Где сейчас ваши решения</div>
            <div className="card__sub">Каждый шаг кликабелен — откроется список с нужным фильтром</div>
          </div>
        </div>
        <div style={{ padding: '12px 16px 16px' }}>
          <div className="pricing-funnel">
            <Link to="/pricing/recommendations?status=new" className="pricing-funnel__step">
              <div className="n">{newCount.toLocaleString('ru-RU')}</div>
              <div className="l">Предложено системой</div>
            </Link>
            <Link to="/pricing/recommendations?status=approved" className="pricing-funnel__step">
              <div className="n">{approvedCount.toLocaleString('ru-RU')}</div>
              <div className="l">Утверждено, ждёт iiko</div>
            </Link>
            <Link to="/pricing/recommendations?status=applied" className="pricing-funnel__step">
              <div className="n">{appliedCount.toLocaleString('ru-RU')}</div>
              <div className="l">Применено, измеряем</div>
            </Link>
            <Link to="/pricing/outcomes" className="pricing-funnel__step">
              <div className="n">{evaluatedCount.toLocaleString('ru-RU')}</div>
              <div className="l">Эффект измерен</div>
            </Link>
          </div>
        </div>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : allWeeks.length === 0 ? (
        <EmptyState text="Данных за период пока нет. Витрины продаж обновляются каждую ночь к 04:30 — загляните позже или выберите другой период." />
      ) : (
        <div className="dash">
          {/* KPI row */}
          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={GLOSSARY.gp}>Валовая прибыль</Term>
              </div>
              <div className="kpi__value">{formatCurrency(cur.gp)}</div>
              <div className="kpi__foot">
                <TrendDelta delta={relDelta(cur.gp, prev.gp)} />
                <span style={{ fontSize: 11 }}>vs пред. период</span>
              </div>
              <div className="kpi__spark">
                <Sparkline data={sparkGp} width={120} height={32} />
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={GLOSSARY.margin}>Маржа</Term>
              </div>
              <div className="kpi__value">{fmtRatioPct(marginCur)}</div>
              <div className="kpi__foot">
                <TrendDelta
                  delta={marginCur != null && marginPrev != null ? (marginCur - marginPrev) * 100 : null}
                  suffix=" п.п."
                />
                <span style={{ fontSize: 11 }}>
                  <Term tip={GLOSSARY.pp}>п.п.</Term> vs пред. период
                </span>
              </div>
              <div className="kpi__spark">
                <Sparkline data={sparkMargin} width={120} height={32} />
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={GLOSSARY.aov}>Средний чек</Term>
              </div>
              <div className="kpi__value">{formatCurrency(aovCur)}</div>
              <div className="kpi__foot">
                <TrendDelta delta={relDelta(aovCur, aovPrev)} />
                <span style={{ fontSize: 11 }}>vs пред. период</span>
              </div>
              <div className="kpi__spark">
                <Sparkline data={sparkAov} width={120} height={32} />
              </div>
            </div>
            <Link to="/pricing/outcomes" className="kpi" style={{ textDecoration: 'none', color: 'inherit' }}>
              <div className="kpi__label">
                <Term tip="Суммарный измеренный эффект применённых цен против ожидания.">Эффект решений</Term>
              </div>
              <div
                className="kpi__value"
                style={{ color: outcomeActual != null && outcomeActual < 0 ? 'var(--neg)' : 'var(--pos)' }}
              >
                {outcomeActual != null && evaluatedCount > 0 ? formatCurrency(outcomeActual) : '—'}
              </div>
              <div className="kpi__foot">
                <span style={{ fontSize: 11 }}>
                  {evaluatedCount > 0
                    ? `факт vs ${outcomeExpected != null ? formatCurrency(outcomeExpected) : '—'} ожидание →`
                    : 'появится после первых применённых цен'}
                </span>
              </div>
            </Link>
          </div>

          {/* Row 2: dynamics chart + top departments */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Динамика по неделям</div>
                  <div className="card__sub">Понедельные агрегаты продаж</div>
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
              <div className="card__header" style={{ borderTop: 'none', paddingTop: 0 }}>
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
              </div>
              <div style={{ padding: '10px 14px 14px', height: 300 }}>
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
                        width={56}
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
                  <div className="card__title">Топ точек по прибыли</div>
                  <div className="card__sub">Клик — переключить точку на всех вкладках</div>
                </div>
              </div>
              {topDepts.length === 0 ? (
                <EmptyState text="Нет данных" />
              ) : (
                <TopDeptsList depts={topDepts} max={topDeptMax} />
              )}
            </div>
          </div>

          {/* Row 3: data quality */}
          <div className="dash-row-2">
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Качество данных</div>
                  <div className="card__sub">Полнота себестоимости</div>
                </div>
              </div>
              <div style={{ padding: '14px 16px' }}>
                <div className="kpi__label">
                  <Term tip={GLOSSARY.costCoverage}>Себестоимость известна</Term>
                </div>
                <div className="kpi__value">
                  {coverageCur != null ? `для ${fmtRatioPct(coverageCur)} выручки` : '—'}
                </div>
                <div className="kpi__foot" style={{ marginTop: 8 }}>
                  <span style={{ fontSize: 11 }}>
                    {coverageCur != null && coverageCur < 0.8
                      ? 'Покрытие низкое: у части блюд нет техкарт — для них рекомендации цен не строятся, а прибыль в отчётах занижена.'
                      : 'Достаточно для расчёта маржи и рекомендаций.'}
                  </span>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Расписание системы</div>
                  <div className="card__sub">Когда обновляются данные</div>
                </div>
              </div>
              <div style={{ padding: '10px 16px 14px', fontSize: 13, color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>· 03:20 — синхронизация цен из iiko + детекция применённых</span>
                <span>· 04:30 — обновление витрин продаж</span>
                <span>· 05:00 — пересчёт ценовых предложений</span>
                <span>· 05:30 — оценка эффекта применённых цен</span>
                <span>· пн 08:00 — недельный отчёт ИИ</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function TrendDelta({ delta, suffix }: { delta: number | null; suffix?: string }) {
  if (delta == null) return <span className="trend">—</span>
  return (
    <span className={cn('trend', delta >= 0 ? 'trend--pos' : 'trend--neg')}>
      {delta >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
      {fmtPctSigned(delta)}{suffix ?? ''}
    </span>
  )
}

function TopDeptsList({
  depts,
  max,
}: {
  depts: { id: string; name: string; gp: number }[]
  max: number
}) {
  const { setDepartmentId } = usePricingScope()
  return (
    <div className="top-list">
      {depts.map((b, i) => (
        <button
          key={b.id}
          type="button"
          className="top-row"
          style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', font: 'inherit', textAlign: 'left' }}
          onClick={() => setDepartmentId(b.id)}
          title={`Выбрать «${b.name}» на всех вкладках`}
        >
          <span className="rank">{String(i + 1).padStart(2, '0')}</span>
          <span className="nm">{b.name}</span>
          <span className="bar">
            <i style={{ width: `${(b.gp / max) * 100}%` }} />
          </span>
          <span className="val">{fmtCompact(b.gp)} ₸</span>
        </button>
      ))}
    </div>
  )
}
