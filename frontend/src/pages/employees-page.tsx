import { useMemo, useState } from 'react'
import { RefreshCw, Search, Users } from 'lucide-react'
import { useEmployees, useSyncEmployees } from '@/hooks/use-employees'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
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
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { formatDate } from '@/lib/formatters'

export function EmployeesPage() {
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('__all__')
  const [includeDeleted, setIncludeDeleted] = useState(false)

  const { data: employees = [], isLoading, error } = useEmployees({
    include_deleted: includeDeleted,
  })
  const syncMutation = useSyncEmployees()

  const roleOptions = useMemo(() => {
    const map = new Map<string, string>()
    employees.forEach((e) => {
      if (!e.main_role_code) return
      const label = e.main_role_name
        ? `${e.main_role_name} (${e.main_role_code})`
        : e.main_role_code
      if (!map.has(e.main_role_code)) {
        map.set(e.main_role_code, label)
      }
    })
    return Array.from(map.entries())
      .map(([code, label]) => ({ code, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [employees])

  const filtered = useMemo(() => {
    let result = employees
    if (roleFilter !== '__all__') {
      result = result.filter((e) => e.main_role_code === roleFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.code && e.code.toLowerCase().includes(q)) ||
          (e.login && e.login.toLowerCase().includes(q)) ||
          (e.email && e.email.toLowerCase().includes(q)),
      )
    }
    return result
  }, [employees, roleFilter, search])

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Сотрудники</h2>
        <Button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
          Обновить справочник
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Должность</Label>
              <Select value={roleFilter} onValueChange={setRoleFilter}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">Все должности</SelectItem>
                  {roleOptions.map((r) => (
                    <SelectItem key={r.code} value={r.code}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Статус</Label>
              <Select
                value={includeDeleted ? 'all' : 'active'}
                onValueChange={(v) => setIncludeDeleted(v === 'all')}
              >
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Только активные</SelectItem>
                  <SelectItem value="all">Включая уволенных</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 flex-1 min-w-[200px]">
              <Label className="text-xs">Поиск</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Поиск по имени, коду, логину, email…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <div className="text-sm text-muted-foreground">
              Найдено: <span className="font-semibold">{filtered.length}</span> из {employees.length}
            </div>
          </div>
          {syncMutation.data && (
            <div className="mt-3 text-sm text-muted-foreground">
              {syncMutation.data.status === 'success'
                ? `Справочник обновлён: добавлено ${syncMutation.data.new ?? 0}, обновлено ${syncMutation.data.updated ?? 0} (всего ${syncMutation.data.total ?? 0}).`
                : `Ошибка: ${syncMutation.data.message}`}
            </div>
          )}
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingSpinner />
      ) : filtered.length === 0 ? (
        <EmptyState text="Сотрудники не найдены" />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Код</TableHead>
                  <TableHead>Имя в системе</TableHead>
                  <TableHead>ФИО</TableHead>
                  <TableHead>Должность</TableHead>
                  <TableHead>Подразделения</TableHead>
                  <TableHead>Логин</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead>Принят</TableHead>
                  <TableHead>Уволен</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((emp) => {
                  const fullName = [emp.last_name, emp.first_name, emp.middle_name]
                    .filter(Boolean)
                    .join(' ')
                  return (
                    <TableRow key={emp.id}>
                      <TableCell className="font-mono text-xs">{emp.code || '—'}</TableCell>
                      <TableCell className="font-medium">{emp.name}</TableCell>
                      <TableCell>{fullName || '—'}</TableCell>
                      <TableCell>
                        {emp.main_role_name || emp.main_role_code ? (
                          <Badge variant="secondary" title={emp.main_role_code || ''}>
                            {emp.main_role_name || emp.main_role_code}
                          </Badge>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-xs">
                        {emp.department_codes && emp.department_codes.length > 0
                          ? emp.department_codes.join(', ')
                          : '—'}
                      </TableCell>
                      <TableCell className="text-xs">{emp.login || '—'}</TableCell>
                      <TableCell className="text-xs">{emp.email || '—'}</TableCell>
                      <TableCell className="text-xs">{emp.cell_phone || '—'}</TableCell>
                      <TableCell className="text-xs">
                        {emp.hire_date ? formatDate(emp.hire_date) : '—'}
                      </TableCell>
                      <TableCell className="text-xs">
                        {emp.fire_date ? formatDate(emp.fire_date) : '—'}
                      </TableCell>
                      <TableCell>
                        {emp.deleted ? (
                          <Badge variant="destructive">уволен</Badge>
                        ) : (
                          <Badge variant="default">активен</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}
    </div>
  )
}
