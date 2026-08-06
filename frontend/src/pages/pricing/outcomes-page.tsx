import { useMemo, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { FlaskConical, RefreshCw, Snowflake, Target } from 'lucide-react'
import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer,
  Tooltip as RTooltip, XAxis, YAxis,
} from 'recharts'

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

/** Прирост продаж — целыми процентами: доли процента здесь ничего не решают. */
function fmtGrowth(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const v = Math.round(value)
  return v < 0 ? `−${Math.abs(v)}%` : `+${v}%`
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
  // не установлен даже знак эффекта. «Не подтверждено» читалось как «провал»,
  // поэтому формулировка та же, что в отчёте: цифра есть, но она мельче ошибки.
  if (!isConfirmed(o)) return { label: 'В пределах погрешности', cls: 'verdict--muted' }
  const expected = o.expected_delta_gp ?? 0
  if (o.incremental_delta_gp >= expected) return { label: 'Лучше плана', cls: 'verdict--pos' }
  if (o.incremental_delta_gp >= 0) return { label: 'В плюсе, ниже плана', cls: 'verdict--warn' }
  return { label: 'В минусе', cls: 'verdict--neg' }
}

/**
 * Подсказка при наведении. Раньше это была строка технических полей через
 * точку («Δ продаж за день (очищ.)», «интервал», «z»), которую нельзя прочитать
 * без знания методики. Теперь — несколько предложений, объясняющих ровно то,
 * что человек и хочет понять: откуда взялся знак эффекта и можно ли ему верить.
 */
function outcomeTooltip(o: PriceOutcome): string {
  if (o.measurable === false) {
    return 'Эффект не считали: продаж слишком мало, не с чем сравнивать. '
      + 'Ноль вместо оценки был бы враньём, поэтому в итог позиция не входит.'
  }
  if (o.incremental_delta_gp == null) {
    return 'Замер ещё идёт. Результат появится через 14 дней после того, '
      + 'как новая цена начала пробиваться в чеках.'
  }

  const ours = o.qty_change_pct != null ? o.qty_change_pct * 100 : null
  const ctl = o.control_qty_change_pct != null ? o.control_qty_change_pct * 100 : null
  const lines: string[] = []

  if (ours != null && ctl != null) {
    lines.push(
      `Продажи за окно: ${fmtNum(o.qty_before)} → ${fmtNum(o.qty_after)} шт, это ${fmtGrowth(ours)} `
      + `к прошлому периоду. То же блюдо в других точках (${o.n_control_stores ?? '—'}), где цену `
      + `не меняли, дало ${fmtGrowth(ctl)}.`,
    )
    lines.push(
      ours >= ctl
        ? 'Мы прибавили больше сети — поэтому эффект в плюсе.'
        : 'Сеть прибавила больше нас — поэтому эффект в минусе, хотя в кассе могло быть и больше денег.',
    )
  }
  if (o.actual_delta_gp != null) {
    lines.push(`В кассе по этой позиции: ${formatCurrency(o.actual_delta_gp)} — это сравнение с прошлым, без поправки на другие точки.`)
  }
  if (o.effect_ci_low != null && o.effect_ci_high != null) {
    lines.push(
      `Точность расчёта: от ${formatCurrency(o.effect_ci_low)} до ${formatCurrency(o.effect_ci_high)}. `
      + (isConfirmed(o)
        ? 'Ноль в этот разброс не попадает — значит знак эффекта установлен.'
        : 'В разброс попадает и ноль, и плюс, и минус — при таких объёмах продаж их не различить.'),
    )
  }
  return lines.join('\n')
}

/** Компактный формат для осей: 50 652 ₸ → «51к». */
function fmtK(v: number): string {
  if (!Number.isFinite(v)) return ''
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)}к`
  return String(Math.round(v))
}

/** Пояснение к каждому столбцу водопада — иначе средний читается наоборот. */
const WATERFALL_EXPLAIN: Record<string, string> = {
  'В кассе': 'На столько выросла прибыль по этим позициям против прошлых двух недель. Сравнение с собой в прошлом.',
  'Минус рост сети': 'Те же блюда в других точках, где цену не меняли, за это время прибавили. Значит и наша прибыль выросла бы примерно настолько же, ничего не делай мы с ценой. Эту величину вычитаем из кассы.',
  'Эффект': 'Что осталось на счёт самого решения о цене: насколько мы разошлись с ростом, который дала бы сеть.',
}

function WaterfallTip({ active, payload }: {
  active?: boolean
  payload?: Array<{ payload: { name: string; value: number } }>
}) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-pop)',
      padding: '8px 11px', maxWidth: 280, fontSize: 12,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 3 }}>
        {p.name}: {formatCurrency(p.value)}
      </div>
      <div style={{ color: 'var(--text-muted)', lineHeight: 1.45 }}>
        {WATERFALL_EXPLAIN[p.name]}
      </div>
    </div>
  )
}

/**
 * Водопад: касса → минус рост сети → эффект.
 *
 * Средний столбец раньше назывался «Фон сети» и показывал −129 912 ₸, из чего
 * читалось «сеть упала». Всё наоборот: сеть выросла на эту величину, и именно
 * поэтому её вычитают из нашего прироста. Название теперь описывает действие,
 * а не сущность, и под графиком стоит вся арифметика одной строкой.
 */
function EffectWaterfall({ cash, effect }: { cash: number; effect: number }) {
  const background = effect - cash
  const data = [
    { name: 'В кассе', range: [Math.min(0, cash), Math.max(0, cash)], tone: cash >= 0 ? 'pos' : 'neg', value: cash },
    {
      name: 'Минус рост сети',
      range: [Math.min(cash, effect), Math.max(cash, effect)],
      tone: background >= 0 ? 'pos' : 'neg',
      value: background,
    },
    { name: 'Эффект', range: [Math.min(0, effect), Math.max(0, effect)], tone: effect >= 0 ? 'pos' : 'neg', value: effect },
  ]

  return (
    <div>
      <div style={{ width: '100%', height: 176 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--chart-axis)' }} stroke="var(--border)" />
            <YAxis tickFormatter={fmtK} tick={{ fontSize: 11, fill: 'var(--chart-axis)' }} stroke="var(--border)" />
            <ReferenceLine y={0} stroke="var(--border-strong)" />
            <RTooltip cursor={{ fill: 'var(--surface-2)' }} content={<WaterfallTip />} />
            <Bar dataKey="range" radius={3}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.tone === 'pos' ? 'var(--pos)' : 'var(--neg)'} fillOpacity={0.75} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs" style={{ color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
        {formatCurrency(cash)} в кассе − {formatCurrency(Math.abs(background))}{' '}
        {background <= 0 ? 'роста сети' : 'падения сети'} = {formatCurrency(effect)}
      </div>
    </div>
  )
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

  // База той же точки, что выбрана в шапке. Раньше карточка всегда показывала
  // сеть: пользователь выбирал «Мадлен 18 мкр», а видел средние по 43 точкам.
  const baselineRow = useMemo<BaselineItem | null>(() => {
    const rows = baseline.data?.items ?? []
    if (rows.length === 0) return null
    const scoped = effectiveDepartmentId
      ? rows.filter((b) => b.scope === 'department' && b.department_id === effectiveDepartmentId)
      : []
    const pool = scoped.length > 0 ? scoped : rows.filter((b) => b.scope === 'network')
    if (pool.length === 0) return null
    return [...pool].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  }, [baseline.data, effectiveDepartmentId])
  const baselineIsNetwork = baselineRow?.scope === 'network'

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

      {/* Разложение итога: почему касса в плюсе, а эффект — нет */}
      {items.length > 0 && s && (
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Откуда берётся итог</div>
              <div className="card__sub">
                Прибыль выросла — но те же блюда в других точках за это время
                выросли сильнее, и этот рост мы бы получили и без всякого приказа.
                Поэтому его вычитают. Что осталось — эффект решения о цене
                {s.decomp_positions < s.total_evaluated
                  && ` · по ${s.decomp_positions} позициям из ${s.total_evaluated}, где эффект измерим`}
              </div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '12px 16px 16px' }}>
            <EffectWaterfall cash={s.decomp_cash} effect={s.batch_effect_gp} />
            <div className="space-y-2 text-sm">
              <Detail label="Прибыль была (за равное число дней)" value={formatCurrency(s.decomp_gp_before)} />
              <Detail label="Прибыль стала" value={formatCurrency(s.decomp_gp_after)} />
              <Detail
                label={s.decomp_cash >= 0 ? '→ выросла на' : '→ снизилась на'}
                value={formatCurrency(Math.abs(s.decomp_cash))}
              />
              <div style={{ borderTop: '1px solid var(--border-faint)', margin: '6px 0' }} />
              {/* Ключевая строка: сеть выросла — вот на сколько. Без неё
                  «была бы без изменения цены» выглядит числом с потолка. */}
              <Detail
                label="Те же блюда в других точках прибавили"
                value={formatCurrency(Math.abs(s.decomp_cash - s.batch_effect_gp))}
              />
              <Detail
                label="→ значит без нашего решения было бы"
                value={formatCurrency(s.decomp_gp_after - s.batch_effect_gp)}
              />
              <Detail
                label={s.batch_effect_gp >= 0 ? '→ превысили это на' : '→ не дотянули до этого на'}
                value={formatCurrency(Math.abs(s.batch_effect_gp))}
              />
            </div>
          </div>
        </div>
      )}

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
                {baselineRow
                  ? `${baselineIsNetwork ? 'вся сеть' : (baselineRow.department_name ?? 'точка')}`
                    + ` · ${baselineRow.label} · ${baselineRow.weeks} нед.`
                  : 'снимок показателей «до»'}
              </div>
            </div>
            <Target size={16} className="text-muted-foreground" />
          </div>
          <div style={{ padding: '14px 16px' }} className="space-y-2 text-sm">
            {baseline.isLoading ? (
              <LoadingSpinner />
            ) : baselineRow ? (
              <>
                <Detail label="Период" value={`${formatDate(baselineRow.baseline_from)} – ${formatDate(baselineRow.baseline_to)}`} />
                <Detail
                  label={
                    <Term tip={baselineIsNetwork ? GLOSSARY.baselineWeeklyGpNetwork : GLOSSARY.baselineWeeklyGp}>
                      {baselineIsNetwork ? 'Прибыль / неделю на точку' : 'Прибыль / неделю'}
                    </Term>
                  }
                  value={formatCurrency(baselineRow.weekly_gp_avg)}
                />
                <Detail
                  label={<Term tip={GLOSSARY.margin}>Маржа</Term>}
                  value={fmtRatioPct(baselineRow.gp_margin)}
                />
                <Detail
                  label={<Term tip={GLOSSARY.aov}>Средний чек</Term>}
                  value={formatCurrency(baselineRow.avg_receipt_sum)}
                />
                <Detail
                  label={
                    <Term tip={baselineIsNetwork ? GLOSSARY.activeSkusNetwork : GLOSSARY.activeSkus}>
                      {baselineIsNetwork ? 'Позиций по всем точкам' : 'Активных позиций'}
                    </Term>
                  }
                  value={fmtNum(baselineRow.active_skus)}
                />
                <Detail
                  label={<Term tip={GLOSSARY.costCoverage}>Себестоимость известна</Term>}
                  value={fmtRatioPct(baselineRow.cost_coverage)}
                />
                {/* Кнопки «Зафиксировать новую базу» здесь нет намеренно: точку
                    отсчёта переставляют раз в несколько месяцев, а место она
                    занимала постоянно. Осталась только в пустом состоянии ниже —
                    там без неё раздел вообще не запустить. Разовая перезаморозка
                    делается через POST /baseline/freeze (есть параметр as_of). */}
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
                «У нас» и «в сети» — насколько изменились продажи в штуках: у этой точки
                и у тех же блюд там, где цену не трогали. Эффект — разница между ними
                в деньгах. Серая цифра значит «посчитали, но ручаться не можем»
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
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.qtyGrowthOurs}>У нас</Term>
                    </TableHead>
                    <TableHead className="text-right">
                      <Term tip={GLOSSARY.qtyGrowthControl}>В сети</Term>
                    </TableHead>
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
                        {/* Две колонки, ради которых вся страница и читается:
                            эффект — это разница между ними, а не «прибыль позиции». */}
                        <TableCell className="text-right tabular whitespace-nowrap">
                          {fmtGrowth(o.qty_change_pct != null ? o.qty_change_pct * 100 : null)}
                        </TableCell>
                        <TableCell
                          className="text-right tabular whitespace-nowrap"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {fmtGrowth(o.control_qty_change_pct != null ? o.control_qty_change_pct * 100 : null)}
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

function Detail({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular">{value}</span>
    </div>
  )
}
