import { useState } from 'react'
import { useBatchForecasts } from '@/hooks/use-forecast'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import { toISODate, daysFromNow, formatDate, formatCurrency } from '@/lib/formatters'
import { Download } from 'lucide-react'

export function ForecastBranchPage() {
  const [fromDate, setFromDate] = useState(toISODate(new Date()))
  const [toDate, setToDate] = useState(daysFromNow(7))
  const [departmentId, setDepartmentId] = useState('__all__')

  const { data, isLoading, error, refetch } = useBatchForecasts({
    from_date: fromDate,
    to_date: toDate,
    department_id: departmentId === '__all__' ? undefined : departmentId,
  })

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Прогноз по филиалам</h2>

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
            Обновить прогноз
          </Button>
        </div>
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.length === 0 ? (
        <EmptyState text="Нет прогнозов за выбранный период" />
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
                <TableHead>Дата</TableHead>
                <TableHead>Филиал</TableHead>
                <TableHead className="text-right">Прогноз продаж</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, idx) => (
                <TableRow key={`${row.date}-${row.department_id}-${idx}`}>
                  <TableCell>{formatDate(row.date)}</TableCell>
                  <TableCell className="font-medium">{row.department_name}</TableCell>
                  <TableCell className="text-right font-mono">
                    {row.predicted_sales != null ? (
                      formatCurrency(row.predicted_sales)
                    ) : (
                      <span className="text-muted-foreground italic">Недостаточно данных</span>
                    )}
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
