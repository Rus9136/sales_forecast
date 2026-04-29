import { useState, useMemo } from 'react'
import { useForecastComparison } from '@/hooks/use-forecast'
import type { ForecastComparison } from '@/types/forecast'
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
import { daysAgo, formatDate, formatCurrency, formatPercent } from '@/lib/formatters'
import { Download, ArrowUpDown } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

type SortKey = keyof ForecastComparison
type SortDir = 'asc' | 'desc'

export function ForecastComparisonPage() {
  const yesterday = daysAgo(1)
  const [fromDate, setFromDate] = useState(daysAgo(30))
  const [toDate, setToDate] = useState(yesterday)
  const [departmentId, setDepartmentId] = useState('__all__')
  const [sortKey, setSortKey] = useState<SortKey>('date')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const { data, isLoading, error, refetch } = useForecastComparison({
    from_date: fromDate,
    to_date: toDate,
    department_id: departmentId === '__all__' ? undefined : departmentId,
  })

  // Sort data
  const sortedData = useMemo(() => {
    if (!data) return []
    return [...data].sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data, sortKey, sortDir])

  // Average error
  const avgError = useMemo(() => {
    if (!data) return null
    const valid = data.filter((d) => d.error_percentage != null)
    if (valid.length === 0) return null
    const sum = valid.reduce((s, d) => s + Math.abs(d.error_percentage!), 0)
    return sum / valid.length
  }, [data])

  // Chart data (limit to 30 points, only for specific department)
  const chartData = useMemo(() => {
    if (!data || departmentId === '__all__') return null
    const byDate = [...data].sort((a, b) => a.date.localeCompare(b.date))
    const limited = byDate.length > 30 ? byDate.slice(-30) : byDate
    return limited.map((d) => ({
      date: d.date,
      predicted: d.predicted_sales,
      actual: d.actual_sales,
    }))
  }, [data, departmentId])

  // Smart scale detection
  const useLogScale = useMemo(() => {
    if (!chartData) return false
    const values = chartData.flatMap((d) => [d.predicted, d.actual].filter((v): v is number => v != null && v > 0))
    if (values.length < 2) return false
    const sorted = [...values].sort((a, b) => a - b)
    const p5 = sorted[Math.floor(sorted.length * 0.05)]
    const p95 = sorted[Math.floor(sorted.length * 0.95)]
    return p95 / Math.max(p5, 1) > 3
  }, [chartData])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const SortableHead = ({ label, column }: { label: string; column: SortKey }) => (
    <TableHead
      className="cursor-pointer select-none hover:text-foreground"
      onClick={() => toggleSort(column)}
    >
      <div className="flex items-center gap-1">
        {label}
        <ArrowUpDown className="h-3 w-3" />
        {sortKey === column && (
          <span className="text-xs">{sortDir === 'asc' ? '\u2191' : '\u2193'}</span>
        )}
      </div>
    </TableHead>
  )

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Сравнение факт / прогноз</h2>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <DateRangePicker
            fromDate={fromDate}
            toDate={toDate}
            onFromDateChange={setFromDate}
            onToDateChange={setToDate}
          />
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
          <Button onClick={() => refetch()}>
            <Download className="h-4 w-4 mr-2" />
            Загрузить
          </Button>
        </div>
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.length === 0 ? (
        <EmptyState text="Нет данных для сравнения за выбранный период" />
      ) : (
        <>
          {/* Average Error Card */}
          {avgError != null && (
            <Card className="bg-gradient-to-r from-[#667eea] to-[#764ba2] text-white">
              <CardContent className="p-6 flex items-center gap-4">
                <div className="text-4xl">📊</div>
                <div>
                  <p className="text-sm opacity-80">Средняя ошибка прогноза</p>
                  <p className="text-3xl font-bold">{formatPercent(avgError)}</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Chart */}
          {chartData && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Прогноз vs Факт
                  {useLogScale && (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      (логарифмическая шкала)
                    </span>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => {
                          const d = new Date(v)
                          return `${d.getDate()}.${d.getMonth() + 1}`
                        }}
                      />
                      <YAxis
                        scale={useLogScale ? 'log' : 'linear'}
                        domain={useLogScale ? ['auto', 'auto'] : [0, 'auto']}
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                        allowDataOverflow={useLogScale}
                      />
                      <Tooltip
                        formatter={(value) => [formatCurrency(Number(value))]}
                        labelFormatter={(label) => formatDate(String(label))}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="predicted"
                        name="Прогноз"
                        stroke="#3498db"
                        strokeWidth={2}
                        dot={{ r: chartData.length > 20 ? 2 : 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="actual"
                        name="Факт"
                        stroke="#27ae60"
                        strokeWidth={2}
                        dot={{ r: chartData.length > 20 ? 2 : 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Sortable Table */}
          <Card>
            <div className="p-4 border-b">
              <span className="text-sm text-muted-foreground">
                Найдено записей: <span className="font-semibold">{sortedData.length}</span>
              </span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead label="Дата" column="date" />
                  <SortableHead label="Филиал" column="department_name" />
                  <SortableHead label="Прогноз" column="predicted_sales" />
                  <SortableHead label="Факт" column="actual_sales" />
                  <SortableHead label="Отклонение" column="error" />
                  <SortableHead label="% Ошибки" column="error_percentage" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedData.map((row, idx) => (
                  <TableRow key={`${row.date}-${row.department_id}-${idx}`}>
                    <TableCell>{formatDate(row.date)}</TableCell>
                    <TableCell className="font-medium">{row.department_name}</TableCell>
                    <TableCell className="text-right font-mono">
                      {row.predicted_sales != null ? formatCurrency(row.predicted_sales) : '—'}
                    </TableCell>
                    <TableCell className="text-right font-mono">{formatCurrency(row.actual_sales)}</TableCell>
                    <TableCell
                      className={`text-right font-mono ${
                        row.error != null ? (row.error >= 0 ? 'text-success' : 'text-destructive') : ''
                      }`}
                    >
                      {row.error != null ? formatCurrency(row.error) : '—'}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono font-semibold ${
                        row.error_percentage != null
                          ? Math.abs(row.error_percentage) > 20
                            ? 'text-destructive'
                            : 'text-success'
                          : ''
                      }`}
                    >
                      {row.error_percentage != null ? formatPercent(row.error_percentage) : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </>
      )}
    </div>
  )
}
