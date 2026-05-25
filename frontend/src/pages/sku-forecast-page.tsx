import { useState, useMemo } from 'react'
import { useSkuBatchForecasts, useSkuModelInfo, useSkuRetrainModel } from '@/hooks/use-sku-forecast'
import { useAuth } from '@/contexts/auth-context'
import type { SkuForecastItem } from '@/types/sku-forecast'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  toISODate,
  daysFromNow,
  formatCurrency,
  formatDate,
} from '@/lib/formatters'
import { ArrowUpDown, UtensilsCrossed, RefreshCw, Loader2 } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

type SortKey = 'product_name' | 'product_type' | 'group_name' | 'category_name' | 'predicted_qty' | 'avg_price' | 'estimated_revenue'
type SortDir = 'asc' | 'desc'

interface AggregatedItem extends SkuForecastItem {
  days_count: number
}

export function SkuForecastPage() {
  const today = toISODate(new Date())
  const weekAhead = daysFromNow(7)

  const [departmentId, setDepartmentId] = useState('')
  const [fromDate, setFromDate] = useState(today)
  const [toDate, setToDate] = useState(weekAhead)
  const [topN, setTopN] = useState('50')
  const [fetchEnabled, setFetchEnabled] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('predicted_qty')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { isAdmin } = useAuth()

  const { data, isLoading, error } = useSkuBatchForecasts(
    fetchEnabled
      ? { department_id: departmentId, from_date: fromDate, to_date: toDate, top_n: Number(topN) }
      : { department_id: undefined, from_date: undefined, to_date: undefined },
  )

  const { data: modelInfo } = useSkuModelInfo()
  const retrainMutation = useSkuRetrainModel()

  const handleLoad = () => {
    if (!departmentId) return
    setFetchEnabled(true)
  }

  const aggregated = useMemo<AggregatedItem[]>(() => {
    if (!data?.daily_forecasts?.length) return []
    const map = new Map<number, AggregatedItem>()
    for (const day of data.daily_forecasts) {
      for (const it of day.items) {
        const existing = map.get(it.product_id)
        if (existing) {
          existing.predicted_qty += it.predicted_qty
          existing.estimated_revenue = (existing.estimated_revenue ?? 0) + (it.estimated_revenue ?? 0)
          existing.days_count += 1
        } else {
          map.set(it.product_id, { ...it, days_count: 1 })
        }
      }
    }
    return Array.from(map.values())
  }, [data])

  const sorted = useMemo(() => {
    return [...aggregated].sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [aggregated, sortKey, sortDir])

  const totalQty = useMemo(() => aggregated.reduce((s, it) => s + it.predicted_qty, 0), [aggregated])
  const totalRevenue = useMemo(() => aggregated.reduce((s, it) => s + (it.estimated_revenue ?? 0), 0), [aggregated])
  const activeSkus = aggregated.length

  const chartData = useMemo(() => {
    const nDays = data?.daily_forecasts?.length || 1
    return [...aggregated]
      .sort((a, b) => b.predicted_qty - a.predicted_qty)
      .slice(0, 10)
      .map((it) => ({
        name: it.product_name.length > 28 ? it.product_name.slice(0, 26) + '…' : it.product_name,
        qty: Math.round((it.predicted_qty / nDays) * 10) / 10,
      }))
      .reverse()
  }, [aggregated, data])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'product_name' ? 'asc' : 'desc')
    }
  }

  const SortableHead = ({ label, column, className }: { label: string; column: SortKey; className?: string }) => (
    <TableHead
      className={`cursor-pointer select-none hover:text-foreground ${className ?? ''}`}
      onClick={() => toggleSort(column)}
    >
      <div className="flex items-center gap-1">
        {label}
        <ArrowUpDown className="h-3 w-3" />
        {sortKey === column && (
          <span className="text-xs">{sortDir === 'asc' ? '↑' : '↓'}</span>
        )}
      </div>
    </TableHead>
  )

  const nDays = data?.daily_forecasts?.length || 1

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Прогноз по блюдам</h1>
          <span className="sub">Прогноз количества продаж по каждому SKU на выбранный период</span>
        </div>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <DepartmentSelect
            value={departmentId}
            onChange={(v) => { setDepartmentId(v); setFetchEnabled(false) }}
            showAll={false}
          />
          <DateRangePicker
            fromDate={fromDate}
            toDate={toDate}
            onFromDateChange={(v) => { setFromDate(v); setFetchEnabled(false) }}
            onToDateChange={(v) => { setToDate(v); setFetchEnabled(false) }}
          />
          <div className="space-y-1">
            <Label className="text-xs">Топ-N</Label>
            <Select value={topN} onValueChange={(v) => { setTopN(v); setFetchEnabled(false) }}>
              <SelectTrigger className="w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleLoad} disabled={!departmentId || isLoading}>
            {isLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <UtensilsCrossed className="h-4 w-4 mr-2" />}
            Загрузить прогноз
          </Button>
        </div>
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {isLoading ? (
        <LoadingSpinner />
      ) : !fetchEnabled || !data ? (
        <EmptyState text="Выберите подразделение и нажмите «Загрузить прогноз»" />
      ) : aggregated.length === 0 ? (
        <EmptyState text="Нет данных о продажах для прогноза. Загрузите историю чеков." />
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Всего прогноз (шт.)</p>
                <p className="text-2xl font-bold" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {Math.round(totalQty).toLocaleString('ru-RU')}
                </p>
                <p className="text-xs text-muted-foreground">за {nDays} {nDays === 1 ? 'день' : nDays < 5 ? 'дня' : 'дней'}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Оценка выручки</p>
                <p className="text-2xl font-bold" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {formatCurrency(totalRevenue)}
                </p>
                <p className="text-xs text-muted-foreground">по текущим ценам</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Активных SKU</p>
                <p className="text-2xl font-bold" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {activeSkus}
                </p>
                <p className="text-xs text-muted-foreground">DISH + GOODS</p>
              </CardContent>
            </Card>
          </div>

          {/* Chart: top-10 by avg daily qty */}
          {chartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Топ-10 по среднесуточному прогнозу (шт/день)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ left: 140, right: 20, top: 5, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        width={140}
                      />
                      <Tooltip
                        formatter={(value) => [`${value} шт/день`, 'Прогноз']}
                        contentStyle={{
                          background: 'var(--surface)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="qty" radius={[0, 4, 4, 0]}>
                        {chartData.map((_, i) => (
                          <Cell key={i} fill="var(--accent)" fillOpacity={0.85} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Table */}
          <Card>
            <div className="p-4 border-b flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                Позиций: <span className="font-semibold">{sorted.length}</span>
                {nDays > 1 && <> &middot; суммы за {nDays} дн.</>}
              </span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead label="Блюдо" column="product_name" />
                  <SortableHead label="Тип" column="product_type" />
                  <SortableHead label="Группа" column="group_name" />
                  <SortableHead label="Категория" column="category_name" />
                  <SortableHead label="Прогноз (шт)" column="predicted_qty" className="text-right" />
                  <SortableHead label="Цена" column="avg_price" className="text-right" />
                  <SortableHead label="Выручка (оц.)" column="estimated_revenue" className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((row) => (
                  <TableRow key={row.product_id}>
                    <TableCell className="font-medium max-w-[300px] truncate">{row.product_name}</TableCell>
                    <TableCell>
                      <Badge variant={row.product_type === 'DISH' ? 'default' : 'secondary'}>
                        {row.product_type === 'DISH' ? 'Блюдо' : 'Товар'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{row.group_name ?? '—'}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{row.category_name ?? '—'}</TableCell>
                    <TableCell className="text-right font-mono" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {row.predicted_qty.toFixed(1)}
                    </TableCell>
                    <TableCell className="text-right font-mono" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {row.avg_price != null ? formatCurrency(row.avg_price) : '—'}
                    </TableCell>
                    <TableCell className="text-right font-mono" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {row.estimated_revenue != null ? formatCurrency(row.estimated_revenue) : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          {/* Model info (admin only) */}
          {isAdmin && modelInfo && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Модель SKU-прогноза</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Статус: </span>
                    <Badge variant={modelInfo.status === 'ready' ? 'default' : 'secondary'}>
                      {modelInfo.status === 'ready' ? 'Обучена' : 'Не обучена'}
                    </Badge>
                  </div>
                  {modelInfo.trained_at && (
                    <div>
                      <span className="text-muted-foreground">Обучена: </span>
                      {formatDate(modelInfo.trained_at.slice(0, 10))}
                    </div>
                  )}
                  {modelInfo.training_metrics?.test_mape != null && (
                    <div>
                      <span className="text-muted-foreground">Test MAPE: </span>
                      <span className="font-mono" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {modelInfo.training_metrics.test_mape.toFixed(1)}%
                      </span>
                    </div>
                  )}
                  {modelInfo.n_features > 0 && (
                    <div>
                      <span className="text-muted-foreground">Признаков: </span>
                      {modelInfo.n_features}
                    </div>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => retrainMutation.mutate({})}
                    disabled={retrainMutation.isPending}
                  >
                    {retrainMutation.isPending
                      ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                    }
                    Переобучить
                  </Button>
                  {retrainMutation.isSuccess && (
                    <span className="text-xs" style={{ color: 'var(--pos)' }}>
                      Модель обучена (MAPE: {(retrainMutation.data as unknown as { metrics: { test_mape: number } })?.metrics?.test_mape?.toFixed(1)}%)
                    </span>
                  )}
                  {retrainMutation.isError && (
                    <span className="text-xs" style={{ color: 'var(--neg)' }}>
                      Ошибка: {(retrainMutation.error as Error).message}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
