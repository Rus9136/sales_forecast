import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { useProductSalesStats } from '@/hooks/use-receipts'
import { daysAgo, toISODate, formatCurrency } from '@/lib/formatters'

export function StatsByProductPage() {
  const [fromDate, setFromDate] = useState(daysAgo(7))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState('__all__')

  const params = useMemo(
    () => ({
      from_date: fromDate,
      to_date: toDate,
      department_id: departmentId === '__all__' ? undefined : departmentId,
      limit: 100,
    }),
    [fromDate, toDate, departmentId],
  )

  const { data, isLoading, error } = useProductSalesStats(params)

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Продажи по блюдам</h1>
          <span className="sub">Топ позиций по выручке за период</span>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <DateRangePicker
              fromDate={fromDate}
              toDate={toDate}
              onFromDateChange={setFromDate}
              onToDateChange={setToDate}
            />
            <DepartmentSelect
              value={departmentId}
              onChange={setDepartmentId}
            />
          </div>
        </CardContent>
      </Card>

      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <div className="kpi">
            <span className="kpi__label">Общая выручка</span>
            <span className="kpi__value">{formatCurrency(data.total_revenue)}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Продано позиций</span>
            <span className="kpi__value">{Math.round(data.total_items_sold).toLocaleString('ru-RU')}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Уникальных блюд</span>
            <span className="kpi__value">{data.items.length}</span>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState text="Нет данных о продажах по блюдам за период" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[40px]">#</TableHead>
                <TableHead>Название</TableHead>
                <TableHead>Группа</TableHead>
                <TableHead>Категория</TableHead>
                <TableHead className="text-right">Продано</TableHead>
                <TableHead className="text-right">Выручка</TableHead>
                <TableHead className="text-right">Ср. цена</TableHead>
                <TableHead className="text-right">Чеков</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((p, idx) => (
                <TableRow key={p.iiko_dish_id ?? `row-${idx}`}>
                  <TableCell className="text-xs text-muted-foreground tabular">{idx + 1}</TableCell>
                  <TableCell className="font-medium text-sm">{p.dish_name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.dish_group || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.dish_category || '—'}</TableCell>
                  <TableCell className="text-right tabular">
                    {Number.isInteger(p.total_qty)
                      ? p.total_qty.toLocaleString('ru-RU')
                      : p.total_qty.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(p.total_sum)}</TableCell>
                  <TableCell className="text-right tabular">
                    {p.avg_price != null ? formatCurrency(p.avg_price) : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular">
                    {p.receipts_count.toLocaleString('ru-RU')}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
