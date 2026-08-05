import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { FlaskConical, RefreshCw, Snowflake, Target } from 'lucide-react'

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
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { Term, GLOSSARY } from '@/components/shared/term'
import {
  useOutcomes, useOutcomesSummary, useBaseline,
  useEvaluateOutcomes, useGenerateExperiments, useFreezeBaseline,
} from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDate } from '@/lib/formatters'
import type { BaselineItem, PriceOutcome } from '@/types/pricing'

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

/** Интервал не накрывает ноль — знак эффекта установлен. */
function isConfirmed(o: PriceOutcome): boolean {
  if (o.effect_ci_low == null || o.effect_ci_high == null) return false
  return o.effect_ci_low > 0 || o.effect_ci_high < 0
}

/** Вывод словами. Сначала — можно ли вообще что-то утверждать. */
function verdictOf(o: PriceOutcome): { label: string; cls: string } {
  if (o.measurable === false) return { label: 'Не измеримо', cls: 'verdict--muted' }
  if (o.incremental_delta_gp == null) return { label: 'В окне измерения', cls: 'verdict--muted' }
  // Штучный торт с разницей в 3 шт. за две недели даёт красивую цифру, за
  // которой нет ничего, кроме случайности. Пока интервал накрывает ноль —
  // не установлен даже знак эффекта.
  if (!isConfirmed(o)) return { label: 'Не подтверждено', cls: 'verdict--muted' }
  const expected = o.expected_delta_gp ?? 0
  if (o.incremental_delta_gp >= expected) return { label: 'Лучше плана', cls: 'verdict--pos' }
  if (o.incremental_delta_gp >= 0) return { label: 'В плюсе, ниже плана', cls: 'verdict--warn' }
  return { label: 'Хуже базы', cls: 'verdict--neg' }
}

function outcomeTooltip(o: PriceOutcome): string {
  if (o.measurable === false) {
    return `Эффект не оценивался: ${o.not_measurable_reason ?? 'не прошли ворота качества'}`
  }
  const parts = [
    `интервал: ${o.effect_ci_low != null ? formatCurrency(o.effect_ci_low) : '—'} … ${o.effect_ci_high != null ? formatCurrency(o.effect_ci_high) : '—'}`,
    `Δ продаж за день (очищ.): ${fmtPctSigned(o.adj_qty_change_pct != null ? o.adj_qty_change_pct * 100 : null)}`,
    `в кассе: ${o.actual_delta_gp != null ? formatCurrency(o.actual_delta_gp) : '—'}`,
    `рабочих дней: ${o.days_before ?? '—'} → ${o.days_after ?? '—'}`,
    `контроль: тот же товар в ${o.n_control_stores ?? '—'} точках`,
  ]
  if (o.p_negative != null) parts.push(`вероятность минуса: ${Math.round(o.p_negative * 100)}%`)
  return parts.join(' · ')
}

function defaultBaselineLabel(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `baseline-${d.getFullYear()}-${m}`
}

export function PricingOutcomesPage() {
  const location = useLocation()
  const { effectiveDepartmentId } = usePricingScope()

  const [expOpen, setExpOpen] = useState(false)
  const [expN, setExpN] = useState(10)
  const [expDelta, setExpDelta] = useState(4)
  const [expResult, setExpResult] = useState<string | null>(null)
  const [evalResult, setEvalResult] = useState<string | null>(null)

  const [freezeOpen, setFreezeOpen] = useState(false)
  const [freezeLabel, setFreezeLabel] = useState(defaultBaselineLabel)
  const [freezeWeeks, setFreezeWeeks] = useState(8)
  const [freezeForce, setFreezeForce] = useState(false)
  const [freezeResult, setFreezeResult] = useState<string | null>(null)

  const summary = useOutcomesSummary(effectiveDepartmentId)
  const outcomes = useOutcomes(effectiveDepartmentId)
  const baseline = useBaseline()
  const evaluate = useEvaluateOutcomes()
  const genExp = useGenerateExperiments()
  const freeze = useFreezeBaseline()

  // Network baseline row of the most recently created label.
  const baselineNet = useMemo<BaselineItem | null>(() => {
    const rows = (baseline.data?.items ?? []).filter((b) => b.scope === 'network')
    if (rows.length === 0) return null
    return [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  }, [baseline.data])

  const s = summary.data
  const effectVsExpected =
    s && s.expected_delta_gp ? s.incremental_delta_gp - s.expected_delta_gp : null

  const runEvaluate = () => {
    setEvalResult(null)
    evaluate.mutate(undefined, {
      onSuccess: (res) =>
        setEvalResult(`Оценено ${res.evaluated}, ещё в 14-дневном окне ${res.pending}, пропущено ${res.skipped}`),
    })
  }

  const runGenerate = () => {
    if (!effectiveDepartmentId) return
    setExpResult(null)
    genExp.mutate(
      { departmentId: effectiveDepartmentId, n: expN, deltaPct: expDelta },
      {
        onSuccess: (res) => {
          setExpResult(`Создано ${res.experiments_created} экспериментов из ${res.candidates} кандидатов`)
          setExpOpen(false)
        },
      },
    )
  }

  const runFreeze = () => {
    setFreezeResult(null)
    freeze.mutate(
      { label: freezeLabel.trim(), weeks: freezeWeeks, force: freezeForce },
      {
        onSuccess: () => {
          setFreezeResult(`База «${freezeLabel.trim()}» зафиксирована (${freezeWeeks} недель).`)
          setFreezeOpen(false)
          setFreezeForce(false)
        },
      },
    )
  }

  const items = outcomes.data?.items ?? []

  if (outcomes.error) return <ErrorAlert message={(outcomes.error as Error).message} />

  const fromPath = { fromPath: location.pathname + location.search }

  return (
    <>
      {/* Действия */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span className="pricing-hint">
          Через 14 дней после применения цены система сравнивает факт с ожиданием — с поправкой
          на <Term tip={GLOSSARY.controlGroup}>контрольную группу</Term> и на число
          рабочих дней точки.
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button
            variant="outline"
            onClick={() => setExpOpen(true)}
            disabled={!effectiveDepartmentId}
          >
            <FlaskConical className="h-4 w-4 mr-2" /> Эксперименты
          </Button>
          <Button variant="outline" onClick={runEvaluate} disabled={evaluate.isPending} title="Оценить эффект по всем точкам">
            <RefreshCw className={`h-4 w-4 mr-2 ${evaluate.isPending ? 'animate-spin' : ''}`} />
            Пересчитать (все точки)
          </Button>
        </div>
      </div>
      {!effectiveDepartmentId && (
        <span className="pricing-hint">
          Для запуска <Term tip={GLOSSARY.experiment}>ценовых экспериментов</Term> выберите точку в шапке раздела.
        </span>
      )}

      {evalResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Оценка:</span> {evalResult}</CardContent></Card>
      )}
      {expResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Эксперименты:</span> {expResult}</CardContent></Card>
      )}
      {freezeResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">База:</span> {freezeResult}</CardContent></Card>
      )}
      {freeze.error && (
        <ErrorAlert
          message={
            apiErrorMessage(freeze.error).includes('409') || /exists|существует/i.test(apiErrorMessage(freeze.error))
              ? `${apiErrorMessage(freeze.error)} — включите «Перезаписать», если хотите заменить существующую базу.`
              : apiErrorMessage(freeze.error)
          }
          title="База не зафиксирована"
        />
      )}

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <div className="kpi">
          <div className="kpi__label">Оценено решений</div>
          <div className="kpi__value">{fmtNum(s?.total_evaluated)}</div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s?.positive_outcomes != null ? `${fmtNum(s.positive_outcomes)} дали прирост прибыли` : 'после окна 14 дней'}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">
            <Term tip={GLOSSARY.incrementalGp}>Эффект решений</Term>
          </div>
          <div
            className="kpi__value"
            style={{ color: s && s.batch_effect_gp >= 0 ? 'var(--pos)' : 'var(--neg)' }}
          >
            {s ? formatCurrency(s.batch_effect_gp) : '—'}
          </div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s
                ? `от ${formatCurrency(s.batch_ci_low)} до ${formatCurrency(s.batch_ci_high)}`
                : 'по приказам целиком'}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">
            <Term tip={GLOSSARY.significance}>Подтверждено измерением</Term>
          </div>
          <div className="kpi__value">
            {s && s.total_evaluated > 0
              ? `${fmtNum(s.significant_outcomes)} из ${fmtNum(s.total_evaluated)}`
              : '—'}
          </div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s && s.significant_outcomes > 0
                ? `надёжный эффект ${formatCurrency(s.significant_delta_gp)}`
                : 'по остальным продаж слишком мало'}
              {s && s.not_measurable > 0 && `, ${fmtNum(s.not_measurable)} без контроля`}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">
            <Term tip={GLOSSARY.cashDeltaGp}>Изменение в кассе</Term>
          </div>
          <div className="kpi__value">
            {s ? formatCurrency(s.actual_delta_gp) : '—'}
          </div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s?.hit_rate != null ? `${fmtRatioPct(s.hit_rate)} позиций в плюсе` : 'фон категории не вычтен'}
            </span>
          </div>
        </div>
      </div>

      {/* Baseline + outcomes */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
        {/* Baseline card */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">
                <Term tip={GLOSSARY.baseline}>База сравнения</Term>
              </div>
              <div className="card__sub">
                {baselineNet ? `${baselineNet.label} · ${baselineNet.weeks} нед.` : 'снимок показателей «до»'}
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
                <Detail label="Прибыль / неделю" value={formatCurrency(baselineNet.weekly_gp_avg)} />
                <Detail label="Маржа" value={fmtRatioPct(baselineNet.gp_margin)} />
                <Detail label="Средний чек" value={formatCurrency(baselineNet.avg_receipt_sum)} />
                <Detail label="Активных позиций" value={fmtNum(baselineNet.active_skus)} />
                <Detail label="Себестоимость известна" value={fmtRatioPct(baselineNet.cost_coverage)} />
                <div style={{ paddingTop: 8 }}>
                  <Button size="sm" variant="outline" onClick={() => { setFreezeLabel(defaultBaselineLabel()); setFreezeOpen(true) }}>
                    <Snowflake className="h-4 w-4 mr-1" /> Зафиксировать новую базу…
                  </Button>
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  База ещё не зафиксирована. Это снимок прибыли, маржи и среднего чека «до» —
                  с ним сравнивается весь эффект изменений цен.
                </p>
                <Button size="sm" onClick={() => { setFreezeLabel(defaultBaselineLabel()); setFreezeOpen(true) }}>
                  <Snowflake className="h-4 w-4 mr-1" /> Зафиксировать базу
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Outcomes table */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Измеренные результаты</div>
              <div className="card__sub">
                Сравнение с теми же блюдами в других точках, где цену не меняли.
                Под суммой — интервал; «Не подтверждено» значит, что он накрывает ноль
              </div>
            </div>
          </div>
          {outcomes.isLoading ? (
            <LoadingSpinner />
          ) : items.length === 0 ? (
            <EmptyState text="Оценённых результатов пока нет — они появляются через 14 дней после применения цены в iiko." />
          ) : (
            <div style={{ maxHeight: 480, overflowY: 'auto' }}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Применено</TableHead>
                    <TableHead>Позиция</TableHead>
                    <TableHead className="text-right">Цена</TableHead>
                    <TableHead className="text-right">Ожидание</TableHead>
                    <TableHead className="text-right">Эффект</TableHead>
                    <TableHead className="text-center">Вывод</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((o) => {
                    const v = verdictOf(o)
                    return (
                      <TableRow key={o.id}>
                        <TableCell className="text-sm whitespace-nowrap">{formatDate(o.applied_at)}</TableCell>
                        <TableCell>
                          <Link
                            to={`/pricing/position/${o.product_id}/${o.department_id}`}
                            state={fromPath}
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
                        <TableCell
                          className="text-right tabular"
                          style={{
                            color: o.incremental_delta_gp == null || !isConfirmed(o)
                              ? 'var(--text-muted)'
                              : o.incremental_delta_gp >= 0 ? 'var(--pos)' : 'var(--neg)',
                            fontWeight: isConfirmed(o) ? 600 : 400,
                          }}
                          title={outcomeTooltip(o)}
                        >
                          {o.incremental_delta_gp != null ? formatCurrency(o.incremental_delta_gp) : '—'}
                          {o.effect_ci_low != null && o.effect_ci_high != null && (
                            <div style={{ fontSize: 10, color: 'var(--text-subtle)', fontWeight: 400 }}>
                              {formatCurrency(o.effect_ci_low)} … {formatCurrency(o.effect_ci_high)}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <span className={`verdict ${v.cls}`} title={outcomeTooltip(o)}>
                            {v.label}
                          </span>
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
              Небольшое контролируемое изменение цены (+2–5%) для блюд, по которым мало
              истории. Цель — <span className="font-medium">измерить чувствительность спроса</span>,
              а не заработать. Все бизнес-правила соблюдаются, решения проходят обычное утверждение.
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
            <Button onClick={runGenerate} disabled={genExp.isPending || !effectiveDepartmentId}>
              {genExp.isPending ? 'Генерация…' : 'Сгенерировать'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Freeze baseline dialog */}
      <Dialog open={freezeOpen} onOpenChange={setFreezeOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Зафиксировать базу сравнения</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Снимок прибыли, маржи и среднего чека за последние полные недели. Дальше все
              результаты будут сравниваться с этой базой. Фиксируйте до массового применения
              новых цен.
            </p>
            <div className="space-y-1">
              <Label className="text-xs">Метка базы</Label>
              <Input value={freezeLabel} onChange={(e) => setFreezeLabel(e.target.value)} className="h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Недель в базе (2–26)</Label>
              <Input
                type="number" min={2} max={26} className="w-24 h-8 tabular"
                value={freezeWeeks}
                onChange={(e) => setFreezeWeeks(Math.min(26, Math.max(2, Number(e.target.value) || 0)))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={freezeForce} onChange={(e) => setFreezeForce(e.target.checked)} />
              Перезаписать, если метка уже существует
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFreezeOpen(false)}>Отмена</Button>
            <Button onClick={runFreeze} disabled={freeze.isPending || !freezeLabel.trim()}>
              {freeze.isPending ? 'Фиксация…' : 'Зафиксировать'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
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
