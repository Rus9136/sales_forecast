import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FlaskConical, RefreshCw, Target } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import {
  useOutcomes, useOutcomesSummary, useBaseline,
  useEvaluateOutcomes, useGenerateExperiments,
} from '@/hooks/use-pricing'
import { formatCurrency, formatDate } from '@/lib/formatters'
import type { BaselineItem } from '@/types/pricing'

const ALL = '__all__'

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function fmtRatioPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return (value * 100).toFixed(0) + '%'
}

function fmtNum(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}

export function PricingOutcomesPage() {
  const [deptId, setDeptId] = useState(ALL)
  const [expOpen, setExpOpen] = useState(false)
  const [expN, setExpN] = useState(10)
  const [expDelta, setExpDelta] = useState(4)
  const [expResult, setExpResult] = useState<string | null>(null)
  const [evalResult, setEvalResult] = useState<string | null>(null)

  const effectiveDept = deptId === ALL ? undefined : deptId

  const summary = useOutcomesSummary(effectiveDept)
  const outcomes = useOutcomes(effectiveDept)
  const baseline = useBaseline()
  const evaluate = useEvaluateOutcomes()
  const genExp = useGenerateExperiments()

  // Network baseline row of the most recently created label.
  const baselineNet = useMemo<BaselineItem | null>(() => {
    const rows = (baseline.data?.items ?? []).filter((b) => b.scope === 'network')
    if (rows.length === 0) return null
    return [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  }, [baseline.data])

  const s = summary.data
  const actualVsExpected =
    s && s.expected_delta_gp ? s.actual_delta_gp - s.expected_delta_gp : null

  const runEvaluate = () => {
    setEvalResult(null)
    evaluate.mutate(undefined, {
      onSuccess: (res) =>
        setEvalResult(`Оценено ${res.evaluated}, в ожидании окна ${res.pending}, пропущено ${res.skipped}`),
    })
  }

  const runGenerate = () => {
    if (!effectiveDept) return
    setExpResult(null)
    genExp.mutate(
      { departmentId: effectiveDept, n: expN, deltaPct: expDelta },
      {
        onSuccess: (res) => {
          setExpResult(`Создано ${res.experiments_created} экспериментов из ${res.candidates} кандидатов`)
          setExpOpen(false)
        },
      },
    )
  }

  const items = outcomes.data?.items ?? []

  if (outcomes.error) return <ErrorAlert message={(outcomes.error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Результаты пилота</h1>
          <span className="sub">Факт vs ожидание по применённым ценам · контрольная группа</span>
        </div>
        <div className="page__actions">
          <DepartmentSelect value={deptId} onChange={setDeptId} includeInactive />
          <Button
            variant="outline"
            onClick={() => setExpOpen(true)}
            disabled={!effectiveDept}
            title={effectiveDept ? 'Сгенерировать ценовые эксперименты' : 'Выберите подразделение'}
          >
            <FlaskConical className="h-4 w-4 mr-2" /> Эксперименты
          </Button>
          <Button variant="outline" onClick={runEvaluate} disabled={evaluate.isPending}>
            <RefreshCw className={`h-4 w-4 mr-2 ${evaluate.isPending ? 'animate-spin' : ''}`} /> Пересчитать
          </Button>
        </div>
      </div>

      {evalResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Оценка:</span> {evalResult}</CardContent></Card>
      )}
      {expResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Эксперименты:</span> {expResult}</CardContent></Card>
      )}

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <div className="kpi">
          <div className="kpi__label">Оценено рекомендаций</div>
          <div className="kpi__value">{fmtNum(s?.total_evaluated)}</div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s?.positive_outcomes != null ? `${fmtNum(s.positive_outcomes)} с приростом GP` : 'после окна 14 дней'}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Фактический ΔGP</div>
          <div
            className="kpi__value"
            style={{ color: s && s.actual_delta_gp >= 0 ? 'var(--pos)' : 'var(--neg)' }}
          >
            {s ? formatCurrency(s.actual_delta_gp) : '—'}
          </div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              ожид. {s ? formatCurrency(s.expected_delta_gp) : '—'}
              {actualVsExpected != null && ` (${actualVsExpected >= 0 ? '+' : ''}${formatCurrency(actualVsExpected)})`}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Hit-rate</div>
          <div className="kpi__value">{fmtRatioPct(s?.hit_rate)}</div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>доля рекомендаций с приростом</span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Реализованная ε</div>
          <div className="kpi__value">
            {s?.avg_realized_elasticity != null ? s.avg_realized_elasticity.toFixed(2) : '—'}
          </div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>средняя по применённым</span>
          </div>
        </div>
      </div>

      {/* Baseline + outcomes */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
        {/* Baseline card */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">База пилота</div>
              <div className="card__sub">
                {baselineNet ? `${baselineNet.label} · ${baselineNet.weeks} нед.` : 'снимок KPI до пилота'}
              </div>
            </div>
            <Target size={16} className="text-muted-foreground" />
          </div>
          <div style={{ padding: '14px 16px' }} className="space-y-2 text-sm">
            {baseline.isLoading ? (
              <LoadingSpinner />
            ) : baselineNet ? (
              <>
                <Detail label="Период" value={`${formatDate(baselineNet.baseline_from)} – ${formatDate(baselineNet.baseline_to)}`} />
                <Detail label="GP / неделю" value={formatCurrency(baselineNet.weekly_gp_avg)} />
                <Detail label="σ недельного GP" value={formatCurrency(baselineNet.weekly_gp_stddev)} />
                <Detail label="GP-маржа" value={fmtRatioPct(baselineNet.gp_margin)} />
                <Detail label="Средний чек" value={formatCurrency(baselineNet.avg_receipt_sum)} />
                <Detail label="Активных SKU" value={fmtNum(baselineNet.active_skus)} />
                <Detail label="Покрытие COGS" value={fmtRatioPct(baselineNet.cost_coverage)} />
              </>
            ) : (
              <EmptyState text="База не заморожена. Зафиксируйте baseline для метрик пилота." />
            )}
          </div>
        </div>

        {/* Outcomes table */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Измеренные результаты</div>
              <div className="card__sub">Δqty скорректирован на контрольную группу той же категории</div>
            </div>
          </div>
          {outcomes.isLoading ? (
            <LoadingSpinner />
          ) : items.length === 0 ? (
            <EmptyState text="Оценённых результатов пока нет — появятся через 14 дней после применения цен." />
          ) : (
            <div style={{ maxHeight: 480, overflowY: 'auto' }}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Применено</TableHead>
                    <TableHead>Позиция</TableHead>
                    <TableHead className="text-right">Цена</TableHead>
                    <TableHead className="text-right">Ожид. ΔGP</TableHead>
                    <TableHead className="text-right">Факт. ΔGP</TableHead>
                    <TableHead className="text-right">Δqty</TableHead>
                    <TableHead className="text-right">Реализ. ε</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((o) => {
                    const hit = (o.actual_delta_gp ?? 0) >= 0
                    return (
                      <TableRow key={o.id}>
                        <TableCell className="text-sm whitespace-nowrap">{formatDate(o.applied_at)}</TableCell>
                        <TableCell>
                          <Link
                            to={`/pricing/position/${o.product_id}/${o.department_id}`}
                            className="text-sm font-medium hover:underline"
                            style={{ color: 'var(--accent)' }}
                          >
                            {o.product_name ?? `#${o.product_id}`}
                          </Link>
                          {o.department_name && (
                            <div className="text-xs text-muted-foreground">{o.department_name}</div>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">
                          {formatCurrency(o.old_price)} → {formatCurrency(o.new_price)}
                        </TableCell>
                        <TableCell className="text-right tabular">
                          {o.expected_delta_gp != null ? formatCurrency(o.expected_delta_gp) : '—'}
                        </TableCell>
                        <TableCell className="text-right tabular" style={{ color: hit ? 'var(--pos)' : 'var(--neg)' }}>
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
        </div>
      </div>

      {/* Experiments dialog */}
      <Dialog open={expOpen} onOpenChange={setExpOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Ценовые эксперименты</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Контролируемое изменение цены для <span className="font-medium">измерения</span> эластичности
              позиций grade C/D (быстрый оборот, без изменений цены ≥28 дней). Все бизнес-правила соблюдаются.
            </p>
            <div className="flex gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Кол-во (≤50)</Label>
                <Input
                  type="number" min={1} max={50} className="w-24 h-8 tabular"
                  value={expN}
                  onChange={(e) => setExpN(Math.min(50, Math.max(1, Number(e.target.value) || 0)))}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Δ цены, % (2–5)</Label>
                <Input
                  type="number" min={2} max={5} step={0.5} className="w-24 h-8 tabular"
                  value={expDelta}
                  onChange={(e) => setExpDelta(Math.min(5, Math.max(2, Number(e.target.value) || 0)))}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExpOpen(false)}>Отмена</Button>
            <Button onClick={runGenerate} disabled={genExp.isPending || !effectiveDept}>
              {genExp.isPending ? 'Генерация…' : 'Сгенерировать'}
            </Button>
          </DialogFooter>
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
