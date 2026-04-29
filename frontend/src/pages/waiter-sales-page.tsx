import { useMemo, useState } from 'react'
import { RefreshCw, Users } from 'lucide-react'
import { useDepartments } from '@/hooks/use-departments'
import {
  useEmployees,
  useSyncEmployees,
  useSyncWaiterSales,
  useWaiterSales,
} from '@/hooks/use-waiter-sales'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { daysAgo, formatCurrency, formatDate, toISODate } from '@/lib/formatters'

export function WaiterSalesPage() {
  const [fromDate, setFromDate] = useState(daysAgo(7))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState('__all__')
  const [search, setSearch] = useState('')

  const { data: departments = [] } = useDepartments(true)
  const { data: employees = [] } = useEmployees(true)
  const deptMap = useMemo(() => new Map(departments.map((d) => [d.id, d.name])), [departments])
  const empMap = useMemo(() => new Map(employees.map((e) => [e.id, e])), [employees])

  const { data, isLoading, error } = useWaiterSales({
    from_date: fromDate,
    to_date: toDate,
    department_id: departmentId === '__all__' ? undefined : departmentId,
    waiter_name: search || undefined,
  })

  const syncWaiters = useSyncWaiterSales()
  const syncEmployees = useSyncEmployees()

  const totals = useMemo(() => {
    if (!data || data.length === 0) return { rows: 0, sum: 0, waiters: 0 }
    const waiters = new Set(data.map((r) => r.waiter_name))
    const sum = data.reduce((acc, r) => acc + (r.total_sales || 0), 0)
    return { rows: data.length, sum, waiters: waiters.size }
  }, [data])

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Продажи по официантам</h2>

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
            <label className="text-xs">Поиск по имени</label>
            <Input
              placeholder="ФИО официанта"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-64"
            />
          </div>
          <Button
            variant="secondary"
            onClick={() =>
              syncWaiters.mutate({
                from_date: fromDate,
                to_date: toDate,
                department_id: departmentId === '__all__' ? undefined : departmentId,
              })
            }
            disabled={syncWaiters.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${syncWaiters.isPending ? 'animate-spin' : ''}`} />
            Синхронизировать продажи
          </Button>
          <Button
            variant="outline"
            onClick={() => syncEmployees.mutate()}
            disabled={syncEmployees.isPending}
          >
            <Users className={`h-4 w-4 mr-2 ${syncEmployees.isPending ? 'animate-pulse' : ''}`} />
            Обновить справочник
          </Button>
        </div>
        {syncWaiters.data && (
          <div className="mt-3 text-sm text-muted-foreground">
            {syncWaiters.data.status === 'success'
              ? `Продажи синхронизированы за ${fromDate}…${toDate}: добавлено ${syncWaiters.data.new ?? 0}, обновлено ${syncWaiters.data.updated ?? 0}${
                  syncWaiters.data.skipped ? `, пропущено ${syncWaiters.data.skipped}` : ''
                }.`
              : `Ошибка синхронизации продаж: ${syncWaiters.data.message}`}
          </div>
        )}
        {syncEmployees.data && (
          <div className="mt-1 text-sm text-muted-foreground">
            {syncEmployees.data.status === 'success'
              ? `Справочник обновлён: добавлено ${syncEmployees.data.new ?? 0}, обновлено ${syncEmployees.data.updated ?? 0} (всего ${syncEmployees.data.total ?? 0}).`
              : `Ошибка обновления справочника: ${syncEmployees.data.message}`}
          </div>
        )}
      </Card>

      {error && <ErrorAlert message={(error as Error).message} />}

      {isLoading ? (
        <LoadingSpinner />
      ) : !data || data.length === 0 ? (
        <EmptyState text="Нет данных за выбранный период" />
      ) : (
        <Card>
          <div className="p-4 border-b flex flex-wrap gap-4 text-sm">
            <span className="text-muted-foreground">
              Записей: <span className="font-semibold text-foreground">{totals.rows}</span>
            </span>
            <span className="text-muted-foreground">
              Уникальных официантов:{' '}
              <span className="font-semibold text-foreground">{totals.waiters}</span>
            </span>
            <span className="text-muted-foreground">
              Сумма:{' '}
              <span className="font-semibold text-foreground">{formatCurrency(totals.sum)}</span>
            </span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Подразделение</TableHead>
                <TableHead>Официант</TableHead>
                <TableHead>Должность</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead className="text-right">Со скидкой</TableHead>
                <TableHead>Привязка</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => {
                const emp = row.employee_id ? empMap.get(row.employee_id) : null
                return (
                  <TableRow key={`${row.department_id}_${row.date}_${row.waiter_name}`}>
                    <TableCell>{formatDate(row.date)}</TableCell>
                    <TableCell className="font-medium">
                      {deptMap.get(row.department_id) || row.department_id}
                    </TableCell>
                    <TableCell>{row.waiter_name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {emp?.main_role_name || emp?.main_role_code || '—'}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatCurrency(row.total_sales)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {row.total_sales_with_discount != null
                        ? formatCurrency(row.total_sales_with_discount)
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {row.employee_id ? (
                        <Badge variant="default">сотрудник</Badge>
                      ) : (
                        <Badge variant="secondary">не найден</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
