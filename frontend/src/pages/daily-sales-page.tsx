import { useState } from 'react'
import { useDailySales } from '@/hooks/use-sales'
import { useDepartments } from '@/hooks/use-departments'
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
import { daysAgo, toISODate, formatDate, formatDateTime, formatCurrency } from '@/lib/formatters'
import { Download } from 'lucide-react'

export function DailySalesPage() {
  const [fromDate, setFromDate] = useState(daysAgo(30))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState('__all__')

  const { data: departments = [] } = useDepartments(true)
  const deptMap = new Map(departments.map((d) => [d.id, d.name]))

  const { data, isLoading, error, refetch } = useDailySales({
    from_date: fromDate,
    to_date: toDate,
    department_id: departmentId === '__all__' ? undefined : departmentId,
  })

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Продажи по дням</h2>

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
                <TableHead className="text-right">Сумма продаж</TableHead>
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
                  <TableCell className="text-right font-mono">{formatCurrency(row.total_sales)}</TableCell>
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
