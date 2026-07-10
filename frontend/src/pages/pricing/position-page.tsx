import { useMemo, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import {
  ArrowLeft, ChefHat, TrendingUp, AlertTriangle,
} from 'lucide-react'
import {
  Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import {
  useSkuPriceHistory, useSkuWeekly, useSkuElasticity, useSkuMenuRole,
  useOverrideMenuRole, useSkuRecommendations, useSkuOutcomes, usePricingRules,
} from '@/hooks/use-pricing'
import { Term, GLOSSARY } from '@/components/shared/term'
import { LlmExplanation } from '@/components/shared/llm-explanation'
import { gradeWord } from '@/lib/pricing-labels'
import { useProduct, useProductRecipe } from '@/hooks/use-menu'
import { apiErrorMessage } from '@/lib/api-client'
import {
  menuRoleLabel, statusLabel, statusBadgeVariant, gradeColor, MENU_ROLE_LABELS,
} from '@/lib/pricing-labels'
import { formatCurrency, formatDate, toISODate } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type { SkuWeeklyItem } from '@/types/pricing'

type PeriodKey = '12' | '26' | '52'
const PERIOD_OPTIONS: { key: PeriodKey; label: string; weeks: number }[] = [
  { key: '12', label: '12 нед.', weeks: 12 },
  { key: '26', label: '26 нед.', weeks: 26 },
  { key: '52', label: 'Год', weeks: 52 },
]

const KEEP_ROLE = '__auto__'

function weekLabel(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}

function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('ru-RU', { maximumFractionDigits: digits })
}

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function fmtRatioPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return (value * 100).toFixed(1) + '%'
}

const LEVEL_LABELS: Record<string, string> = {
  sku: 'по самому блюду',
  group: 'по группе блюд',
  global: 'по всему меню',
}

export function PricingPositionPage() {
  const params = useParams<{ productId: string; departmentId: string }>()
  const location = useLocation()
  const productId = Number(params.productId)
  const departmentId = params.departmentId ?? ''

  // Возврат туда, откуда пришли (рекомендации / аналитика / результаты)
  const backPath =
    (location.state as { fromPath?: string } | null)?.fromPath ?? '/pricing/recommendations'

  const [period, setPeriod] = useState<PeriodKey>('52')
  const [recipeOpen, setRecipeOpen] = useState(false)

  const weeks = PERIOD_OPTIONS.find((p) => p.key === period)!.weeks
  const fromWeek = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - weeks * 7)
    return toISODate(d)
  }, [weeks])

  const product = useProduct(Number.isFinite(productId) ? productId : null)
  const weekly = useSkuWeekly({ productId, departmentId, fromWeek })
  const priceHistory = useSkuPriceHistory({ productId, departmentId })
  const elasticity = useSkuElasticity({ productId, departmentId })
  const menuRole = useSkuMenuRole({ productId, departmentId })
  const recs = useSkuRecommendations({ productId, departmentId })
  const outcomes = useSkuOutcomes({ productId, departmentId })
  const recipe = useProductRecipe(recipeOpen ? productId : null)
  const overrideRole = useOverrideMenuRole()
  const rules = usePricingRules()

  // Реальный порог маржи из правила min_margin (fail-safe дефолт 60%)
  const minMargin = useMemo(() => {
    const rule = (rules.data?.items ?? []).find(
      (r) => r.rule_type === 'min_margin' && r.scope_type === 'global' && !r.scope_id && r.is_active,
    )
    const v = rule?.params && typeof rule.params.value === 'number' ? rule.params.value : null
    return v ?? 0.6
  }, [rules.data])

  const weeklyRows = useMemo<SkuWeeklyItem[]>(
    () => [...(weekly.data?.items ?? [])].sort((a, b) => a.week_start.localeCompare(b.week_start)),
    [weekly.data],
  )

  // ── Derived metrics ────────────────────────────────────────────
  const newestRec = useMemo(() => {
    const items = [...(recs.data ?? [])]
    items.sort((a, b) => b.created_at.localeCompare(a.created_at))
    return items[0] ?? null
  }, [recs.data])

  const openRec = useMemo(
    () => (recs.data ?? []).find((r) => r.status === 'new') ?? null,
    [recs.data],
  )

  const latestWeek = weeklyRows.length ? weeklyRows[weeklyRows.length - 1] : null
  const latestPriceEvent = useMemo(() => {
    const items = [...(priceHistory.data?.items ?? [])]
    items.sort((a, b) => b.last_seen_date.localeCompare(a.last_seen_date))
    return items[0] ?? null
  }, [priceHistory.data])

  const currentPrice =
    newestRec?.current_price ?? latestPriceEvent?.price ?? latestWeek?.avg_price ?? null

  const totals = useMemo(() => {
    let qty = 0, revenue = 0, cost = 0
    let coveredQty = 0
    for (const w of weeklyRows) {
      qty += w.total_qty
      revenue += w.total_revenue
      cost += w.total_cost
      if (w.total_cost > 0) coveredQty += w.total_qty
    }
    return { qty, revenue, cost, coveredQty }
  }, [weeklyRows])

  const unitCost =
    newestRec?.cogs ??
    (totals.qty > 0 && totals.cost > 0 ? totals.cost / totals.qty : null)
  const gpMargin =
    currentPrice && unitCost != null && currentPrice > 0
      ? (currentPrice - unitCost) / currentPrice
      : latestWeek?.gp_margin ?? null
  const weeksWithSales = weeklyRows.filter((w) => w.total_qty > 0).length
  const avgQtyWeek = weeksWithSales > 0 ? totals.qty / weeksWithSales : null

  // ── Price + volume chart ───────────────────────────────────────
  const trendData = useMemo(
    () =>
      weeklyRows.map((w) => ({
        week: w.week_start,
        label: weekLabel(w.week_start),
        qty: w.total_qty,
        price: w.avg_price,
      })),
    [weeklyRows],
  )

  // ── Demand curve Q(P) = Q0·(P/P0)^ε with CI band ───────────────
  const demandCurve = useMemo(() => {
    const eMean = elasticity.data?.elasticity_mean
    if (currentPrice == null || avgQtyWeek == null || eMean == null) return null
    const P0 = currentPrice
    const Q0 = avgQtyWeek
    const eLo = elasticity.data?.elasticity_ci_lower ?? eMean
    const eHi = elasticity.data?.elasticity_ci_upper ?? eMean
    const points: { price: number; qty: number; ciRange: [number, number] }[] = []
    const steps = 24
    for (let i = 0; i <= steps; i++) {
      const ratio = 0.82 + (i / steps) * 0.36 // 0.82 → 1.18
      const P = P0 * ratio
      const q = Q0 * Math.pow(ratio, eMean)
      const qA = Q0 * Math.pow(ratio, eLo)
      const qB = Q0 * Math.pow(ratio, eHi)
      points.push({
        price: P,
        qty: q,
        ciRange: [Math.min(qA, qB), Math.max(qA, qB)],
      })
    }
    return points
  }, [elasticity.data, currentPrice, avgQtyWeek])

  // ── Guards ─────────────────────────────────────────────────────
  if (!Number.isFinite(productId) || !departmentId) {
    return <ErrorAlert message="Некорректный адрес позиции" />
  }

  const productName =
    product.data?.name ??
    newestRec?.product_name ??
    elasticity.data?.product_name ??
    latestWeek?.product_name ??
    `#${productId}`
  const departmentName =
    newestRec?.department_name ?? latestWeek?.department_name ?? 'Подразделение'

  const role = menuRole.data?.effective_role ?? newestRec?.menu_role ?? null
  const grade = elasticity.data?.reliability_grade ?? null

  const onRoleChange = (value: string) => {
    overrideRole.mutate({
      productId,
      departmentId,
      manualRole: value === KEEP_ROLE ? '' : value,
    })
  }

  const isLoading = weekly.isLoading && !weekly.data
  const hasData = weeklyRows.length > 0 || priceHistory.data?.items.length || elasticity.data

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <div className="flex items-center gap-2">
            <Link to={backPath} className="btn-ghost btn-icon-sm" title="Назад">
              <ArrowLeft size={16} />
            </Link>
            <h1>{productName}</h1>
          </div>
          <span className="sub">
            {departmentName}
            {product.data?.category_name ? ` · ${product.data.category_name}` : ''}
            {product.data?.code ? ` · код ${product.data.code}` : ''}
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
          <Button variant="outline" onClick={() => setRecipeOpen(true)}>
            <ChefHat className="h-4 w-4 mr-2" /> Техкарта
          </Button>
        </div>
      </div>

      {/* Role badge + override */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs uppercase text-muted-foreground">Роль в меню</span>
        <Select
          value={menuRole.data?.manual_role ?? KEEP_ROLE}
          onValueChange={onRoleChange}
          disabled={overrideRole.isPending || !menuRole.data}
        >
          <SelectTrigger className="w-52 h-8">
            <SelectValue>
              <Badge variant="outline">{menuRoleLabel(role)}</Badge>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={KEEP_ROLE}>
              Авто ({menuRoleLabel(menuRole.data?.auto_role)})
            </SelectItem>
            {Object.entries(MENU_ROLE_LABELS).map(([key, label]) => (
              <SelectItem key={key} value={key}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {menuRole.data?.manual_role && (
          <span className="text-xs text-muted-foreground">ручное переопределение</span>
        )}
        {overrideRole.error && (
          <span className="text-xs" style={{ color: 'var(--neg)' }}>
            Не удалось изменить роль: {apiErrorMessage(overrideRole.error)}
          </span>
        )}
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : !hasData ? (
        <EmptyState text="Нет данных по этой позиции в выбранном подразделении." />
      ) : (
        <>
          {/* KPI row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <div className="kpi">
              <div className="kpi__label">Текущая цена</div>
              <div className="kpi__value">{formatCurrency(currentPrice)}</div>
              <div className="kpi__foot">
                <span style={{ fontSize: 11 }}>
                  {latestPriceEvent ? `изм. ${formatDate(latestPriceEvent.last_seen_date)}` : 'из каталога'}
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Себестоимость</div>
              <div className="kpi__value">{formatCurrency(unitCost)}</div>
              <div className="kpi__foot">
                <span style={{ fontSize: 11 }}>
                  {totals.qty > 0 && totals.coveredQty < totals.qty
                    ? `покрытие ${fmtRatioPct(totals.coveredQty / totals.qty)}`
                    : 'на единицу'}
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={GLOSSARY.margin}>Маржа</Term>
              </div>
              <div className="kpi__value">{fmtRatioPct(gpMargin)}</div>
              <div className="kpi__foot">
                <span style={{ fontSize: 11 }}>
                  {gpMargin != null && gpMargin < minMargin
                    ? `ниже порога ${(minMargin * 100).toFixed(0)}% из правила «Минимальная маржа»`
                    : 'валовая маржа'}
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={GLOSSARY.elasticity}>Чувствительность спроса</Term>
              </div>
              <div className="kpi__value" style={{ color: gradeColor(grade) }}>
                {elasticity.data ? elasticity.data.elasticity_mean.toFixed(2) : '—'}
              </div>
              <div className="kpi__foot">
                <span style={{ fontSize: 11 }}>
                  {elasticity.data
                    ? `${gradeWord(grade)} надёжность · оценка ${LEVEL_LABELS[elasticity.data.estimation_level] ?? elasticity.data.estimation_level}${avgQtyWeek != null ? ` · ${fmtNum(avgQtyWeek)} шт/нед` : ''}`
                    : 'нет оценки'}
                </span>
              </div>
            </div>
          </div>

          {/* Row 2: price+volume chart | elasticity panel */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">История цены и объёма</div>
                  <div className="card__sub">Понедельно · средняя цена и количество</div>
                </div>
              </div>
              <div style={{ padding: '10px 14px 14px', height: 320 }}>
                {trendData.length === 0 ? (
                  <EmptyState text="Нет недельных данных за период" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={trendData}>
                      <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                        stroke="var(--chart-axis)"
                        minTickGap={20}
                      />
                      <YAxis
                        yAxisId="qty"
                        tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                        stroke="var(--chart-axis)"
                        width={40}
                      />
                      <YAxis
                        yAxisId="price"
                        orientation="right"
                        tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                        stroke="var(--chart-axis)"
                        tickFormatter={(v) => fmtNum(Number(v))}
                        width={52}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--surface)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          fontSize: 12,
                          color: 'var(--text)',
                        }}
                        formatter={(value, name) =>
                          name === 'Цена'
                            ? [formatCurrency(Number(value)), name]
                            : [fmtNum(Number(value)), name]
                        }
                        labelFormatter={(l) => `Неделя ${l}`}
                      />
                      <Bar
                        yAxisId="qty"
                        dataKey="qty"
                        name="Количество"
                        fill="var(--accent)"
                        fillOpacity={0.28}
                        radius={[2, 2, 0, 0]}
                      />
                      <Line
                        yAxisId="price"
                        type="monotone"
                        dataKey="price"
                        name="Цена"
                        stroke="var(--accent)"
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Эластичность спроса</div>
                  <div className="card__sub">Оценка и доверительный интервал</div>
                </div>
              </div>
              <div style={{ padding: '14px 16px' }} className="space-y-3 text-sm">
                {elasticity.data ? (
                  <>
                    <Detail label="Оценка ε" value={elasticity.data.elasticity_mean.toFixed(3)} />
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">
                        <Term tip={GLOSSARY.ci}>95% интервал</Term>
                      </span>
                      <span className="tabular">
                        [{elasticity.data.elasticity_ci_lower.toFixed(2)}; {elasticity.data.elasticity_ci_upper.toFixed(2)}]
                      </span>
                    </div>
                    <Detail
                      label="Уровень оценки"
                      value={LEVEL_LABELS[elasticity.data.estimation_level] ?? elasticity.data.estimation_level}
                    />
                    <Detail label="Изменений цены в истории" value={fmtNum(elasticity.data.n_price_events)} />
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">
                        <Term tip={GLOSSARY.grade}>Надёжность</Term>
                      </span>
                      <span style={{ color: gradeColor(grade), fontWeight: 600 }}>
                        {gradeWord(grade)} · {grade}
                      </span>
                    </div>
                    <div
                      className="text-xs rounded-md p-2"
                      style={{ background: 'var(--surface-2)', color: 'var(--text-muted)' }}
                    >
                      {elasticity.data.elasticity_ci_upper < 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <TrendingUp size={12} /> Весь CI &lt; 0 — спрос реагирует на цену.
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <AlertTriangle size={12} /> CI включает 0 — измеримого ценового сигнала мало.
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <EmptyState text="Эластичность для этой пары ещё не оценена" />
                )}
              </div>
            </div>
          </div>

          {/* Demand curve */}
          {demandCurve && (
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Кривая спроса</div>
                  <div className="card__sub">
                    Сколько порций в неделю купят при другой цене. Сейчас — {fmtNum(avgQtyWeek)} шт/нед
                    при {formatCurrency(currentPrice)}; светлый веер — <Term tip={GLOSSARY.ci}>коридор неопределённости</Term>
                  </div>
                </div>
              </div>
              <div style={{ padding: '10px 14px 14px', height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={demandCurve}>
                    <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="price"
                      type="number"
                      domain={['dataMin', 'dataMax']}
                      tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                      stroke="var(--chart-axis)"
                      tickFormatter={(v) => fmtNum(Number(v))}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                      stroke="var(--chart-axis)"
                      tickFormatter={(v) => fmtNum(Number(v))}
                      width={44}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        fontSize: 12,
                        color: 'var(--text)',
                      }}
                      formatter={(value, name) => {
                        if (name === 'Спрос') return [fmtNum(Number(value), 1) + ' шт/нед', name]
                        if (Array.isArray(value)) {
                          return [`${fmtNum(Number(value[0]), 1)} – ${fmtNum(Number(value[1]), 1)}`, '95% CI']
                        }
                        return [fmtNum(Number(value), 1), name]
                      }}
                      labelFormatter={(l) => `Цена ${formatCurrency(Number(l))}`}
                    />
                    <Area
                      dataKey="ciRange"
                      stroke="none"
                      fill="var(--accent)"
                      fillOpacity={0.12}
                      name="95% CI"
                      legendType="none"
                    />
                    <Line
                      type="monotone"
                      dataKey="qty"
                      name="Спрос"
                      stroke="var(--accent)"
                      strokeWidth={2}
                      dot={false}
                    />
                    {currentPrice != null && (
                      <ReferenceLine
                        x={currentPrice}
                        stroke="var(--text-muted)"
                        strokeDasharray="4 4"
                        label={{ value: 'тек.', fontSize: 10, fill: 'var(--text-muted)', position: 'top' }}
                      />
                    )}
                    {openRec?.recommended_price != null && (
                      <ReferenceLine
                        x={openRec.recommended_price}
                        stroke="var(--pos)"
                        strokeDasharray="4 4"
                        label={{ value: 'реком.', fontSize: 10, fill: 'var(--pos)', position: 'top' }}
                      />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Recommendations for this SKU */}
          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Рекомендации по позиции</div>
                <div className="card__sub">История ценовых предложений оптимизатора</div>
              </div>
            </div>
            {(recs.data ?? []).length === 0 ? (
              <EmptyState text="Рекомендаций по этой позиции нет" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата</TableHead>
                    <TableHead className="text-right">Тек. цена</TableHead>
                    <TableHead className="text-right">Реком.</TableHead>
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.deltaPct}>Δ%</Term>
                    </TableHead>
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.deltaGp}>Ожид. ΔGP</Term>
                    </TableHead>
                    <TableHead className="text-center">
                      <Term tip={GLOSSARY.elasticity}>ε</Term>
                    </TableHead>
                    <TableHead className="text-center">Статус</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...(recs.data ?? [])]
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .map((r) => {
                      const up = (r.delta_pct ?? 0) >= 0
                      const gpUp = (r.delta_gp ?? 0) >= 0
                      return (
                        <TableRow key={r.id}>
                          <TableCell className="text-sm">{formatDate(r.created_at)}</TableCell>
                          <TableCell className="text-right tabular">{formatCurrency(r.current_price)}</TableCell>
                          <TableCell className="text-right tabular font-medium">{formatCurrency(r.recommended_price)}</TableCell>
                          <TableCell className="text-right tabular" style={{ color: up ? 'var(--pos)' : 'var(--neg)' }}>
                            {fmtPctSigned(r.delta_pct)}
                          </TableCell>
                          <TableCell className="text-right tabular" style={{ color: gpUp ? 'var(--pos)' : 'var(--neg)' }}>
                            {r.delta_gp != null ? formatCurrency(r.delta_gp) : '—'}
                          </TableCell>
                          <TableCell className="text-center" style={{ color: gradeColor(r.elasticity_grade) }}>
                            {r.elasticity_grade ?? '—'}
                          </TableCell>
                          <TableCell className="text-center">
                            <Badge variant={statusBadgeVariant(r.status)}>
                              {statusLabel(r.status)}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                </TableBody>
              </Table>
            )}
            {/* LLM explanation of the open recommendation */}
            {openRec && (
              <div className="border-t p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Обоснование (ИИ)
                </div>
                <LlmExplanation rec={openRec} />
              </div>
            )}
          </div>

          {/* Measured outcomes (feedback loop) */}
          {(outcomes.data ?? []).length > 0 && (
            <div className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">Измеренный эффект</div>
                  <div className="card__sub">Факт vs ожидание после применения · контрольная группа</div>
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Применено</TableHead>
                    <TableHead className="text-right">Цена</TableHead>
                    <TableHead className="text-right">Ожидание, ₸/нед</TableHead>
                    <TableHead className="text-right">Факт, ₸/нед</TableHead>
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.controlGroup}>Δ продаж (скорр.)</Term>
                    </TableHead>
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.realizedElasticity}>Факт. ε</Term>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(outcomes.data ?? []).map((o) => {
                    const hit = o.actual_delta_gp != null ? o.actual_delta_gp >= 0 : null
                    return (
                      <TableRow key={o.recommendation_id}>
                        <TableCell className="text-sm">{formatDate(o.applied_at)}</TableCell>
                        <TableCell className="text-right tabular">
                          {formatCurrency(o.old_price)} → {formatCurrency(o.new_price)}
                        </TableCell>
                        <TableCell className="text-right tabular">
                          {o.expected_delta_gp != null ? formatCurrency(o.expected_delta_gp) : '—'}
                        </TableCell>
                        <TableCell
                          className="text-right tabular"
                          style={{ color: hit == null ? 'var(--text-muted)' : hit ? 'var(--pos)' : 'var(--neg)' }}
                        >
                          {o.actual_delta_gp != null ? formatCurrency(o.actual_delta_gp) : '—'}
                        </TableCell>
                        <TableCell className="text-right tabular">{fmtPctSigned(o.adj_qty_change_pct)}</TableCell>
                        <TableCell className="text-right tabular">
                          {o.realized_elasticity != null ? o.realized_elasticity.toFixed(2) : '—'}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}

      {/* Recipe dialog */}
      <Dialog open={recipeOpen} onOpenChange={setRecipeOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ChefHat className="h-5 w-5" /> Техкарта: {productName}
            </DialogTitle>
          </DialogHeader>
          {recipe.isLoading ? (
            <LoadingSpinner />
          ) : recipe.data ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Действует с:</span> {recipe.data.date_from}
                </div>
                <div>
                  <span className="text-muted-foreground">Выход:</span> {recipe.data.assembled_amount}
                </div>
                {recipe.data.description && (
                  <div className="col-span-2">
                    <span className="text-muted-foreground">Описание:</span> {recipe.data.description}
                  </div>
                )}
              </div>
              {recipe.data.ingredients.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ингредиент</TableHead>
                      <TableHead className="text-right">Брутто</TableHead>
                      <TableHead className="text-right">Нетто</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recipe.data.ingredients.map((ing) => (
                      <TableRow key={ing.id}>
                        <TableCell>
                          <div className="text-sm font-medium">{ing.ingredient_name || '—'}</div>
                          {ing.ingredient_code && (
                            <div className="text-xs text-muted-foreground font-mono">{ing.ingredient_code}</div>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular">{ing.amount_in}</TableCell>
                        <TableCell className="text-right tabular">{ing.amount_out ?? '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState text="В техкарте нет ингредиентов" />
              )}
            </div>
          ) : (
            <EmptyState text="Техкарта не найдена" />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular">{value}</span>
    </div>
  )
}
