import { useState } from 'react'
import { useAutoSyncStatus, useSyncSales, useTestAutoSync } from '@/hooks/use-sync'
import type { SyncResult } from '@/hooks/use-sync'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import { daysAgo, toISODate, formatDate, formatDateTime } from '@/lib/formatters'
import { RefreshCw, Play, Clock, BarChart3, Zap, CheckCircle, XCircle } from 'lucide-react'

export function SyncPage() {
  const [fromDate, setFromDate] = useState(daysAgo(1))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState('__all__')
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [syncProgress, setSyncProgress] = useState(0)

  const { data: status, isLoading: statusLoading, error: statusError, refetch: refetchStatus } = useAutoSyncStatus()
  const syncMutation = useSyncSales()
  const testMutation = useTestAutoSync()

  const handleSync = async () => {
    setSyncResult(null)
    setSyncProgress(20)

    try {
      const result = await syncMutation.mutateAsync({
        from_date: fromDate,
        to_date: toDate,
        department_id: departmentId === '__all__' ? undefined : departmentId,
      })
      setSyncProgress(100)
      setSyncResult(result)
      refetchStatus()
    } catch (err) {
      setSyncProgress(0)
      setSyncResult({
        status: 'error',
        message: (err as Error).message || 'Ошибка синхронизации',
        from_date: fromDate,
        to_date: toDate,
        error_type: 'connection_error',
      })
    }
  }

  const handleTestSync = async () => {
    try {
      await testMutation.mutateAsync()
      refetchStatus()
    } catch {
      // Error handled by mutation state
    }
  }

  const stats = status?.statistics

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Синхронизация данных</h2>

      {statusError && <ErrorAlert message={(statusError as Error).message} />}

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Расписание
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-sm">
              <p>Время синхронизации: <span className="font-semibold">02:00</span></p>
              <p>Период загрузки: <span className="font-semibold">Предыдущий день</span></p>
              <div className="flex items-center gap-1 mt-2">
                <CheckCircle className="h-4 w-4 text-success" />
                <span className="text-success font-medium">Планировщик активен</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Статистика (30 дн.)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {statusLoading ? (
              <div className="text-sm text-muted-foreground">Загрузка...</div>
            ) : stats ? (
              <div className="space-y-1 text-sm">
                <p>Успешных: <span className="font-semibold text-success">{stats.success_count_30d}</span></p>
                <p>Ошибок: <span className="font-semibold text-destructive">{stats.error_count_30d}</span></p>
                <p>Успешность: <span className="font-semibold">{stats.success_rate_30d.toFixed(1)}%</span></p>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Нет данных</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Zap className="h-4 w-4" />
              Быстрые действия
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestSync}
                disabled={testMutation.isPending}
              >
                <Play className="h-4 w-4 mr-2" />
                {testMutation.isPending ? 'Запуск...' : 'Тестовый запуск'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => refetchStatus()}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Обновить статус
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Latest Sync Info */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stats.latest_success && (
            <Card className="border-success/30">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-success mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium">Последняя успешная синхронизация</p>
                    <p className="text-muted-foreground">
                      {formatDateTime(stats.latest_success.executed_at)}
                    </p>
                    <p className="text-muted-foreground">
                      Записей: {stats.latest_success.records}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          {stats.latest_error && (
            <Card className="border-destructive/30">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <XCircle className="h-5 w-5 text-destructive mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium">Последняя ошибка</p>
                    <p className="text-muted-foreground">
                      {formatDateTime(stats.latest_error.executed_at)}
                    </p>
                    <p className="text-destructive">
                      {stats.latest_error.message}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Manual Sync Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ручная синхронизация</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <DateRangePicker
              fromDate={fromDate}
              toDate={toDate}
              onFromDateChange={setFromDate}
              onToDateChange={setToDate}
            />
            <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
            <Button onClick={handleSync} disabled={syncMutation.isPending}>
              <RefreshCw className={`h-4 w-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
              {syncMutation.isPending ? 'Синхронизация...' : 'Загрузить'}
            </Button>
          </div>

          {/* Progress */}
          {syncMutation.isPending && (
            <div className="space-y-2">
              <Progress value={syncProgress} />
              <p className="text-sm text-muted-foreground">Синхронизация данных о продажах...</p>
            </div>
          )}

          {/* Result */}
          {syncResult && (
            <Alert variant={syncResult.status === 'success' ? 'success' : 'destructive'}>
              {syncResult.status === 'success' ? (
                <CheckCircle className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              <AlertTitle>
                {syncResult.status === 'success' ? 'Синхронизация завершена' : 'Ошибка синхронизации'}
              </AlertTitle>
              <AlertDescription>
                <p>{syncResult.message}</p>
                {syncResult.status === 'success' && (
                  <div className="mt-2 space-y-1 text-sm">
                    <p>Период: {formatDate(syncResult.from_date)} — {formatDate(syncResult.to_date)}</p>
                    {syncResult.total_raw_records != null && (
                      <p>Сырых записей: {syncResult.total_raw_records}</p>
                    )}
                    {syncResult.summary_records != null && (
                      <p>Дневных итогов: {syncResult.summary_records}</p>
                    )}
                    {syncResult.hourly_records != null && (
                      <p>Часовых записей: {syncResult.hourly_records}</p>
                    )}
                  </div>
                )}
                {syncResult.status === 'error' && syncResult.error_type && (
                  <div className="mt-2 text-sm">
                    <p>Тип ошибки: {syncResult.error_type}</p>
                    <ul className="list-disc list-inside mt-1 space-y-0.5">
                      <li>Проверьте подключение к серверу iiko</li>
                      <li>Убедитесь, что даты указаны правильно</li>
                      <li>Попробуйте уменьшить диапазон дат</li>
                    </ul>
                  </div>
                )}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Sync History */}
      {statusLoading ? (
        <LoadingSpinner />
      ) : status && status.logs.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">История синхронизаций</CardTitle>
          </CardHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата выполнения</TableHead>
                <TableHead>Период данных</TableHead>
                <TableHead>Тип</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Записей</TableHead>
                <TableHead>Сообщение</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {status.logs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="text-sm">{formatDateTime(log.executed_at)}</TableCell>
                  <TableCell className="text-sm">{formatDate(log.sync_date)}</TableCell>
                  <TableCell>
                    <Badge variant={log.sync_type === 'auto' ? 'secondary' : 'default'}>
                      {log.sync_type === 'auto' ? 'Авто' : 'Ручная'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={log.status === 'success' ? 'success' : 'destructive'}>
                      {log.status === 'success' ? 'Успех' : 'Ошибка'}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {log.total_raw_records || log.summary_records || 0}
                  </TableCell>
                  <TableCell className="text-sm max-w-xs truncate" title={log.message}>
                    {log.message}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : null}
    </div>
  )
}
