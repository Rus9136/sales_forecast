import { useState, useMemo } from 'react'
import { useHourlySales } from '@/hooks/use-sales'
import { useDepartments } from '@/hooks/use-departments'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { daysAgo, toISODate, formatDate, formatDateTime, formatCurrency } from '@/lib/formatters'
import { Download } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

export function HourlySalesPage() {
  const [fromDate, setFromDate] = useState(daysAgo(7))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState('__all__')
  const [hour, setHour] = useState('__all__')

  const { data: departments = [] } = useDepartments(true)
  const deptMap = new Map(departments.map((d) => [d.id, d.name]))

  const { data, isLoading, error, refetch } = useHourlySales({
    from_date: fromDate,
    to_date: toDate,
    department_id: departmentId === '__all__' ? undefined : departmentId,
    hour: hour === '__all__' ? undefined : hour,
  })

  // Aggregate by hour for chart
  const chartData = useMemo(() => {
    if (!data || departmentId === '__all__') return null
    const byHour: Record<number, number> = {}
    for (let h = 0; h < 24; h++) byHour[h] = 0
    for (const row of data) {
      byHour[row.hour] = (byHour[row.hour] || 0) + row.sales_amount
    }
    return Array.from({ length: 24 }, (_, h) => ({
      hour: `${h}:00`,
      amount: byHour[h],
    }))
  }, [data, departmentId])

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Продажи по часам</h2>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <DateRangePicker
            fromDate={fromDate}
            toDate={toDate}
            onFromDateChange={setFromDate}
            onToDateChange={setToDate}
          />
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
          <div className="space-y-1">
            <Label className="text-xs">Час</Label>
            <Select value={hour} onValueChange={setHour}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Все</SelectItem>
                {Array.from({ length: 24 }, (_, h) => (
                  <SelectItem key={h} value={String(h)}>
                    {`${h}:00`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => refetch()}>
            <Download className="h-4 w-4 mr-2" />
            Загрузить
          </Button>
        </div>
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {/* Chart - only for specific department */}
      {chartData && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Распределение продаж по часам</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tick={{ fontSize: 12 }} />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    formatter={(value) => [formatCurrency(Number(value)), 'Продажи']}
                  />
                  <Bar dataKey="amount" fill="#3498db" radius={[4, 4, 0, 0]} opacity={0.8} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.length === 0 ? (
        <EmptyState text="Нет данных за выбранный период" />
      ) : (
        <Card>
          <div className="p-4 border-b">
            <span className="text-sm text-muted-foreground">
              Найдено записей: <span className="font-semibold">{data.length}</span>
            </span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Подразделение</TableHead>
                <TableHead>Дата</TableHead>
                <TableHead>Час</TableHead>
                <TableHead className="text-right">Прайс</TableHead>
                <TableHead className="text-right">К оплате</TableHead>
                <TableHead>Создано</TableHead>
                <TableHead>Синхронизировано</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-xs text-muted-foreground">{row.id}</TableCell>
                  <TableCell className="font-medium">{deptMap.get(row.department_id) || row.department_id}</TableCell>
                  <TableCell>{formatDate(row.date)}</TableCell>
                  <TableCell>{`${row.hour}:00`}</TableCell>
                  <TableCell className="text-right font-mono">{formatCurrency(row.sales_amount)}</TableCell>
                  <TableCell className="text-right font-mono">
                    {row.paid_amount != null ? formatCurrency(row.paid_amount) : '—'}
                  </TableCell>
                  <TableCell className="text-xs">{formatDateTime(row.created_at)}</TableCell>
                  <TableCell className="text-xs">{formatDateTime(row.synced_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
