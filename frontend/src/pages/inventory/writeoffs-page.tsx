import { useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { X } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { Term } from '@/components/shared/term'
import {
  useWriteoffByProduct, useWriteoffSummary, useWriteoffTrend,
} from '@/hooks/use-inventory'
import { daysAgo, formatCurrency, formatDate, toISODate } from '@/lib/formatters'

const TIPS = {
  writeoff:
    'Акт списания — документ, которым товар снимается с остатков без продажи: истёк срок, порча, угощение, расходники. Себестоимость такого товара уходит в убыток.',
  shareOfRevenue:
    'Сколько копеек с каждого рубля выручки сгорает в списаниях. Ориентир для кондитерской точки — до 1,5–2%.',
  shareOfSupply:
    'Какая доля всего привезённого на точку товара не дошла до кассы, а была списана.',
  lossRate:
    'Потери позиции: списанное количество, делённое на привезённое за тот же период. 40% значит, что из каждых 10 привезённых штук 4 ушли в списание.',
}

function LossBadge({ rate }: { rate: number | null }) {
  if (rate === null) return <span className="text-muted-foreground">—</span>
  const pct = `${(rate * 100).toFixed(0)}%`
  if (rate >= 0.3) return <Badge variant="destructive">{pct}</Badge>
  if (rate >= 0.1) return <Badge variant="secondary">{pct}</Badge>
  return <span className="num">{pct}</span>
}

export function WriteoffsPage() {
  const [departmentId, setDepartmentId] = useState('')
  const [fromDate, setFromDate] = useState(daysAgo(30))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [reasonId, setReasonId] = useState<string | null>(null)
  const [storeId, setStoreId] = useState<string | null>(null)

  const period = useMemo(
    () => ({ department_id: departmentId, from_date: fromDate, to_date: toDate }),
    [departmentId, fromDate, toDate],
  )
  const hasDept = Boolean(departmentId)

  const summary = useWriteoffSummary(period, hasDept)
  const trend = useWriteoffTrend(period, hasDept)
  const products = useWriteoffByProduct(
    { ...period, reason_id: reasonId ?? undefined, store_id: storeId ?? undefined, limit: 50 },
    hasDept,
  )

  const error = summary.error || trend.error || products.error
  const activeFilter = reasonId || storeId
  const activeRow = summary.data?.breakdown.find(
    (b) => (reasonId ? b.reason_id === reasonId : true) && (storeId ? b.store_id === storeId : true),
  )

  const topReason = summary.data?.breakdown[0]

  const chartData = (trend.data ?? []).map((p) => ({
    week: formatDate(p.week).slice(0, 5),
    cost: p.writeoff_cost,
    share: p.share_of_revenue !== null ? p.share_of_revenue * 100 : null,
  }))

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Списания</h1>
          <span className="sub">
            Что уходит в убыток вместо кассы — по складам, причинам и позициям
          </span>
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
            <DateRangePicker
              fromDate={fromDate}
              toDate={toDate}
              onFromDateChange={setFromDate}
              onToDateChange={setToDate}
            />
          </div>
        </CardContent>
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {!hasDept && (
        <Card className="mt-4">
          <CardContent className="p-4">
            <EmptyState text="Выберите подразделение, чтобы увидеть списания" />
          </CardContent>
        </Card>
      )}

      {hasDept && summary.isLoading && <LoadingSpinner />}

      {hasDept && summary.data && (
        <>
          <div className="grid gap-3 mt-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="kpi">
              <div className="kpi__label">
                <Term tip={TIPS.writeoff}>Списано за период</Term>
              </div>
              <div className="kpi__value">{formatCurrency(summary.data.total_writeoff_cost)}</div>
              <div className="kpi__foot">
                {formatDate(summary.data.from_date)} — {formatDate(summary.data.to_date)}
              </div>
            </div>

            <div className="kpi">
              <div className="kpi__label">
                <Term tip={TIPS.shareOfRevenue}>Доля от выручки</Term>
              </div>
              <div className="kpi__value">
                {summary.data.writeoff_share_of_revenue !== null
                  ? `${(summary.data.writeoff_share_of_revenue * 100).toFixed(2)}%`
                  : '—'}
              </div>
              <div className="kpi__foot">выручка {formatCurrency(summary.data.revenue)}</div>
            </div>

            <div className="kpi">
              <div className="kpi__label">
                <Term tip={TIPS.shareOfSupply}>Доля от прихода</Term>
              </div>
              <div className="kpi__value">
                {summary.data.writeoff_share_of_supply !== null
                  ? `${(summary.data.writeoff_share_of_supply * 100).toFixed(2)}%`
                  : '—'}
              </div>
              <div className="kpi__foot">привезено {formatCurrency(summary.data.supply_cost)}</div>
            </div>

            <div className="kpi">
              <div className="kpi__label">Главная причина</div>
              <div className="kpi__value" style={{ fontSize: 18, lineHeight: 1.3 }}>
                {topReason?.reason ?? '—'}
              </div>
              <div className="kpi__foot">
                {topReason
                  ? `${formatCurrency(topReason.cost)} · ${(topReason.share_of_total * 100).toFixed(0)}% всех потерь`
                  : 'нет данных'}
              </div>
            </div>
          </div>

          {chartData.length > 0 && (
            <Card className="mt-4">
              <div className="card__header">
                <div>
                  <div className="card__title">Динамика по неделям</div>
                  <div className="card__sub">Стоимость списаний, ₸</div>
                </div>
              </div>
              <CardContent className="p-4 pt-0">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                    <XAxis dataKey="week" tick={{ fill: 'var(--chart-axis)', fontSize: 12 }} />
                    <YAxis
                      tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                      tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                    />
                    <Tooltip
                      formatter={(v) => formatCurrency(Number(v))}
                      labelFormatter={(l) => `Неделя с ${String(l)}`}
                      contentStyle={{
                        background: 'var(--surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        color: 'var(--text)',
                      }}
                    />
                    <Bar dataKey="cost" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          <Card className="mt-4">
            <div className="card__header">
              <div>
                <div className="card__title">Склад и причина</div>
                <div className="card__sub">Нажмите на строку, чтобы отфильтровать позиции ниже</div>
              </div>
            </div>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Склад</TableHead>
                    <TableHead>Причина</TableHead>
                    <TableHead className="text-right">Актов</TableHead>
                    <TableHead className="text-right">Позиций</TableHead>
                    <TableHead className="text-right">Сумма</TableHead>
                    <TableHead className="text-right">Доля</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.data.breakdown.map((row) => {
                    const selected = row.reason_id === reasonId && row.store_id === storeId
                    return (
                      <TableRow
                        key={`${row.store_id}-${row.reason_id}`}
                        onClick={() => {
                          if (selected) {
                            setReasonId(null)
                            setStoreId(null)
                          } else {
                            setReasonId(row.reason_id)
                            setStoreId(row.store_id)
                          }
                        }}
                        className="cursor-pointer"
                        data-state={selected ? 'selected' : undefined}
                      >
                        <TableCell>{row.store_name}</TableCell>
                        <TableCell>{row.reason}</TableCell>
                        <TableCell className="text-right num">{row.documents}</TableCell>
                        <TableCell className="text-right num">{row.positions}</TableCell>
                        <TableCell className="text-right num">{formatCurrency(row.cost)}</TableCell>
                        <TableCell className="text-right num">
                          {(row.share_of_total * 100).toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="mt-4">
            <div className="card__header">
              <div>
                <div className="card__title">Что именно списываем</div>
                <div className="card__sub">Топ позиций по стоимости потерь</div>
              </div>
              {activeFilter && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setReasonId(null)
                    setStoreId(null)
                  }}
                >
                  {activeRow ? `${activeRow.store_name} · ${activeRow.reason}` : 'Фильтр'}
                  <X className="ml-1 h-3 w-3" />
                </Button>
              )}
            </div>
            <CardContent className="p-0">
              {products.isLoading && <LoadingSpinner />}
              {!products.isLoading && (products.data?.length ?? 0) === 0 && (
                <EmptyState text="За период по этому фильтру списаний нет" />
              )}
              {(products.data?.length ?? 0) > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Позиция</TableHead>
                      <TableHead className="text-right">Списано</TableHead>
                      <TableHead className="text-right">Привезено</TableHead>
                      <TableHead className="text-right">
                        <Term tip={TIPS.lossRate}>Потери</Term>
                      </TableHead>
                      <TableHead className="text-right">Сумма</TableHead>
                      <TableHead>Причины</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {products.data!.map((p) => (
                      <TableRow key={p.product_id}>
                        <TableCell className="max-w-[320px] truncate" title={p.product_name}>
                          {p.product_name}
                        </TableCell>
                        <TableCell className="text-right num">
                          {p.written_amount.toLocaleString('ru-RU')} {p.unit ?? ''}
                        </TableCell>
                        <TableCell className="text-right num">
                          {p.supplied_amount !== null
                            ? p.supplied_amount.toLocaleString('ru-RU')
                            : '—'}
                        </TableCell>
                        <TableCell className="text-right">
                          <LossBadge rate={p.loss_rate} />
                        </TableCell>
                        <TableCell className="text-right num">
                          {formatCurrency(p.written_cost)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate">
                          {p.reasons.join(', ')}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
