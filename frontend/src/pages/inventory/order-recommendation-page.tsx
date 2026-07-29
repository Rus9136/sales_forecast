import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Download, TrendingDown, TrendingUp } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { DepartmentSelect } from '@/components/shared/department-select'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { Term } from '@/components/shared/term'
import { useInventorySuppliers, useOrderRecommendation } from '@/hooks/use-inventory'
import { daysAgo, formatCurrency, formatDate, toISODate } from '@/lib/formatters'
import type { OrderRecommendationItem } from '@/types/inventory'

const ALL = '__all__'

const TIPS = {
  serviceLevel:
    'Целевой уровень сервиса: в какой доле дней заказа должно хватить. Считается из наценки позиции — упущенная продажа дорогого торта обходится дороже, чем его же списание, поэтому по маржинальным позициям выгодно возить с запасом.',
  recommended:
    'Рекомендуемый объём на выбранный день. Берётся распределение продаж этого же дня недели за окно истории, из него — квантиль на уровне сервиса.',
  currentPractice:
    'Сколько в среднем привозят в этот день недели сейчас — по фактическим приходным накладным.',
  stockout:
    'Дни, когда позиция закончилась: последняя продажа прошла более чем за 3 часа до последнего чека точки, и списаний в этот день не было.',
  saving:
    'Наблюдаемые деньги: сокращаем заказ ровно в пределах того, что фактически уходило в списание.',
  upside:
    'Оценка сверху: предполагает, что весь добавленный объём продастся. Настоящий спрос в дни дефицита неизвестен — мы знаем только, что он был выше проданного.',
  confidence:
    'Надёжность оценки: high — 6+ наблюдений и мало дефицитных дней; low — данных мало либо спрос почти всегда упирался в поставку.',
}

const CONFIDENCE_LABEL: Record<string, string> = {
  high: 'высокая',
  medium: 'средняя',
  low: 'низкая',
}

function ConfidenceBadge({ value }: { value: string }) {
  if (value === 'high') return <Badge variant="outline">{CONFIDENCE_LABEL[value]}</Badge>
  if (value === 'medium') return <Badge variant="secondary">{CONFIDENCE_LABEL[value]}</Badge>
  return <Badge variant="destructive">{CONFIDENCE_LABEL[value]}</Badge>
}

function toCsv(items: OrderRecommendationItem[], targetDate: string): string {
  const head = [
    'Позиция', 'Ед', 'Рекомендуем', 'Возим сейчас', 'Разница',
    'Уровень сервиса', 'Дней дефицита', 'Списано за окно', 'Причина',
  ]
  const rows = items.map((i) => [
    `"${i.product_name.replace(/"/g, '""')}"`,
    i.unit ?? '',
    i.recommended_qty,
    i.current_practice_qty ?? '',
    i.delta_qty ?? '',
    i.service_level,
    i.stockout_days,
    i.written_qty_period,
    `"${i.reason}"`,
  ])
  return [`Заявка на ${targetDate}`, head.join(';'), ...rows.map((r) => r.join(';'))].join('\n')
}

export function OrderRecommendationPage() {
  const [departmentId, setDepartmentId] = useState('')
  const [targetDate, setTargetDate] = useState(toISODate(new Date()))
  const [supplierId, setSupplierId] = useState(ALL)
  const [minSum, setMinSum] = useState(5000)

  const suppliersPeriod = useMemo(
    () => ({ department_id: departmentId, from_date: daysAgo(56), to_date: toISODate(new Date()) }),
    [departmentId],
  )
  const suppliers = useInventorySuppliers(suppliersPeriod, Boolean(departmentId))

  // По умолчанию — крупнейший поставщик точки: обычно это и есть цех.
  useEffect(() => {
    if (supplierId === ALL && suppliers.data?.length) {
      setSupplierId(suppliers.data[0].supplier_id ?? ALL)
    }
  }, [suppliers.data, supplierId])

  const recommendation = useOrderRecommendation(
    {
      department_id: departmentId,
      target_date: targetDate,
      supplier_id: supplierId === ALL ? undefined : supplierId,
      min_supplied_sum: minSum,
    },
    Boolean(departmentId),
  )

  const data = recommendation.data
  const decrease = (data?.items ?? []).filter((i) => (i.delta_qty ?? 0) < 0)
  const increase = (data?.items ?? []).filter((i) => (i.delta_qty ?? 0) > 0)

  function downloadCsv() {
    if (!data) return
    const blob = new Blob(['﻿' + toCsv(data.items, data.target_date)], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `zayavka_${data.target_date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Заявка на цех</h1>
          <span className="sub">
            Сколько заказывать на день, чтобы не списывать излишки и не терять продажи
          </span>
        </div>
        <div className="page__actions">
          <Button variant="outline" onClick={downloadCsv} disabled={!data?.items.length}>
            <Download className="mr-1 h-4 w-4" /> Выгрузить
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <DepartmentSelect
              value={departmentId}
              onChange={setDepartmentId}
              showAll={false}
              includeInactive
            />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="target-date">Дата заявки</Label>
              <Input
                id="target-date"
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="w-[170px]"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Поставщик</Label>
              <Select value={supplierId} onValueChange={setSupplierId}>
                <SelectTrigger className="w-[260px]">
                  <SelectValue placeholder="Все поставщики" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все поставщики</SelectItem>
                  {(suppliers.data ?? []).map((s) => (
                    <SelectItem key={s.supplier_id ?? 'none'} value={s.supplier_id ?? 'none'}>
                      {s.supplier_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="min-sum">Порог поставки, ₸</Label>
              <Input
                id="min-sum"
                type="number"
                min={0}
                step={1000}
                value={minSum}
                onChange={(e) => setMinSum(Number(e.target.value) || 0)}
                className="w-[140px]"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {recommendation.error && <ErrorAlert message={(recommendation.error as Error).message} />}

      {!departmentId && (
        <Card className="mt-4">
          <CardContent className="p-4">
            <EmptyState text="Выберите подразделение, чтобы собрать заявку" />
          </CardContent>
        </Card>
      )}

      {departmentId && recommendation.isLoading && <LoadingSpinner />}

      {data && (
        <>
          <div className="grid gap-3 mt-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="kpi">
              <div className="kpi__label">Позиций в заявке</div>
              <div className="kpi__value">{data.totals.positions}</div>
              <div className="kpi__foot">
                история {formatDate(data.lookback_from)} — {formatDate(data.lookback_to)}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Снизить / увеличить</div>
              <div className="kpi__value">
                {data.totals.positions_to_decrease} / {data.totals.positions_to_increase}
              </div>
              <div className="kpi__foot">
                <Term tip={TIPS.stockout}>дефицит</Term> на {data.totals.positions_with_stockout} поз.
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={TIPS.saving}>Экономия от снижения</Term>
              </div>
              <div className="kpi__value">{formatCurrency(data.totals.saving_from_reduction)}</div>
              <div className="kpi__foot">по фактическим списаниям</div>
            </div>
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={TIPS.upside}>Потенциал от увеличения</Term>
              </div>
              <div className="kpi__value">{formatCurrency(data.totals.upside_from_increase)}</div>
              <div className="kpi__foot">оценка сверху, не гарантия</div>
            </div>
          </div>

          {data.warnings.length > 0 && (
            <Alert className="mt-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                <ul className="list-disc pl-4 space-y-0.5">
                  {data.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <OrderTable
            title="Заказывать меньше"
            subtitle="Позиции, которые регулярно уходят в списание"
            icon={<TrendingDown className="h-4 w-4" style={{ color: 'var(--neg)' }} />}
            items={decrease}
            mode="decrease"
          />

          <OrderTable
            title="Заказывать больше"
            subtitle="Позиции, которые заканчиваются задолго до закрытия"
            icon={<TrendingUp className="h-4 w-4" style={{ color: 'var(--pos)' }} />}
            items={increase}
            mode="increase"
          />
        </>
      )}
    </div>
  )
}

function OrderTable({
  title, subtitle, icon, items, mode,
}: {
  title: string
  subtitle: string
  icon: React.ReactNode
  items: OrderRecommendationItem[]
  mode: 'decrease' | 'increase'
}) {
  return (
    <Card className="mt-4">
      <div className="card__header">
        <div className="flex items-center gap-2">
          {icon}
          <div>
            <div className="card__title">{title}</div>
            <div className="card__sub">{subtitle}</div>
          </div>
        </div>
        <span className="text-sm text-muted-foreground num">{items.length} поз.</span>
      </div>
      <CardContent className="p-0">
        {items.length === 0 ? (
          <EmptyState text="Здесь пусто — по этой группе корректировок нет" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Позиция</TableHead>
                <TableHead className="text-right">
                  <Term tip={TIPS.recommended}>Заказать</Term>
                </TableHead>
                <TableHead className="text-right">
                  <Term tip={TIPS.currentPractice}>Возим сейчас</Term>
                </TableHead>
                <TableHead className="text-right">Δ</TableHead>
                <TableHead className="text-right">
                  <Term tip={TIPS.serviceLevel}>Сервис</Term>
                </TableHead>
                <TableHead className="text-right">
                  {mode === 'decrease' ? 'Списано' : 'Дней дефицита'}
                </TableHead>
                <TableHead className="text-right">
                  {mode === 'decrease' ? (
                    <Term tip={TIPS.saving}>Экономия</Term>
                  ) : (
                    <Term tip={TIPS.upside}>Потенциал</Term>
                  )}
                </TableHead>
                <TableHead className="text-right">
                  <Term tip={TIPS.confidence}>Надёжность</Term>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((i) => (
                <TableRow key={i.product_id}>
                  <TableCell className="max-w-[300px]">
                    <div className="truncate" title={i.product_name}>
                      {i.product_name}
                    </div>
                    <div className="text-xs text-muted-foreground truncate">{i.reason}</div>
                  </TableCell>
                  <TableCell className="text-right num font-medium">
                    {i.recommended_qty.toLocaleString('ru-RU')} {i.unit ?? ''}
                  </TableCell>
                  <TableCell className="text-right num text-muted-foreground">
                    {i.current_practice_qty !== null
                      ? i.current_practice_qty.toLocaleString('ru-RU')
                      : '—'}
                  </TableCell>
                  <TableCell
                    className="text-right num"
                    style={{ color: (i.delta_qty ?? 0) < 0 ? 'var(--neg)' : 'var(--pos)' }}
                  >
                    {i.delta_qty !== null
                      ? `${i.delta_qty > 0 ? '+' : ''}${i.delta_qty.toLocaleString('ru-RU')}`
                      : '—'}
                  </TableCell>
                  <TableCell className="text-right num">
                    {(i.service_level * 100).toFixed(0)}%
                  </TableCell>
                  <TableCell className="text-right num">
                    {mode === 'decrease'
                      ? i.written_qty_period.toLocaleString('ru-RU')
                      : i.stockout_days}
                  </TableCell>
                  <TableCell className="text-right num">
                    {formatCurrency(
                      mode === 'decrease'
                        ? i.saving_from_reduction ?? 0
                        : i.upside_from_increase ?? 0,
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <ConfidenceBadge value={i.confidence} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
