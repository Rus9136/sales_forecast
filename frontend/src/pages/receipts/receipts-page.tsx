import { useMemo, useState } from 'react'
import { RefreshCw, Search, Receipt as ReceiptIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { useReceipts, useReceiptDetail, useSyncReceipts } from '@/hooks/use-receipts'
import { KNOWN_IIKO_SOURCES, iikoSourceLabel } from '@/lib/iiko-sources'
import {
  daysAgo,
  toISODate,
  formatCurrency,
  formatDate,
  formatDateTime,
} from '@/lib/formatters'

const ALL = '__all__'
const PAGE_SIZE = 100

export function ReceiptsPage() {
  const [fromDate, setFromDate] = useState(daysAgo(7))
  const [toDate, setToDate] = useState(toISODate(new Date()))
  const [departmentId, setDepartmentId] = useState(ALL)
  const [source, setSource] = useState(ALL)
  const [waiterSearch, setWaiterSearch] = useState('')
  const [page, setPage] = useState(0)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const filters = useMemo(
    () => ({
      from_date: fromDate,
      to_date: toDate,
      department_id: departmentId === ALL ? undefined : departmentId,
      iiko_source_domain: source === ALL ? undefined : source,
      waiter_name: waiterSearch.trim() || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [fromDate, toDate, departmentId, source, waiterSearch, page],
  )

  const { data: receipts = [], isLoading, error } = useReceipts(filters)
  const detail = useReceiptDetail(selectedId, selectedDate)
  const syncMutation = useSyncReceipts()

  const totals = useMemo(() => {
    const sum = receipts.reduce((a, r) => a + r.total_sum, 0)
    const disc = receipts.reduce((a, r) => a + r.discount_sum, 0)
    const items = receipts.reduce((a, r) => a + r.items_count, 0)
    return { sum, disc, items, count: receipts.length }
  }, [receipts])

  const onSync = async () => {
    try {
      await syncMutation.mutateAsync({
        from_date: fromDate,
        to_date: toDate,
        department_id: departmentId === '__all__' ? undefined : departmentId,
      })
    } catch {
      /* rendered via mutation state */
    }
  }

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Чеки</h1>
          <span className="sub">
            Детализация заказов по позициям из iiko
          </span>
        </div>
        <div className="page__actions">
          <Button
            variant="outline"
            onClick={onSync}
            disabled={syncMutation.isPending}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`}
            />
            {syncMutation.isPending ? 'Загрузка…' : 'Синхронизация'}
          </Button>
        </div>
      </div>

      {syncMutation.data && (
        <Card>
          <CardContent className="p-3 text-sm">
            <span className="font-medium">Результат:</span>{' '}
            {syncMutation.data.total_receipts} чеков ·{' '}
            {syncMutation.data.total_items} позиций из{' '}
            {syncMutation.data.per_domain.length} источников
            {syncMutation.data.errors.length > 0 && (
              <span className="ml-2 text-destructive">
                ({syncMutation.data.errors.length} ошибок)
              </span>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <DateRangePicker
              fromDate={fromDate}
              toDate={toDate}
              onFromDateChange={(v) => { setFromDate(v); setPage(0) }}
              onToDateChange={(v) => { setToDate(v); setPage(0) }}
            />
            <DepartmentSelect
              value={departmentId}
              onChange={(v) => { setDepartmentId(v); setPage(0) }}
            />
            <div className="space-y-1">
              <Label className="text-xs">Источник iiko</Label>
              <Select value={source} onValueChange={(v) => { setSource(v); setPage(0) }}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все источники</SelectItem>
                  {KNOWN_IIKO_SOURCES.map((host) => (
                    <SelectItem key={host} value={host}>
                      {iikoSourceLabel(host)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs">Официант</label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Поиск по имени"
                  value={waiterSearch}
                  onChange={(e) => { setWaiterSearch(e.target.value); setPage(0) }}
                  className="pl-9 w-56"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* KPI row */}
      {!isLoading && receipts.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <div className="kpi">
            <span className="kpi__label">Чеков на странице</span>
            <span className="kpi__value">{totals.count}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Сумма</span>
            <span className="kpi__value">{formatCurrency(totals.sum)}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Скидки</span>
            <span className="kpi__value">{formatCurrency(totals.disc)}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Позиций</span>
            <span className="kpi__value">{totals.items.toLocaleString('ru-RU')}</span>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner />
      ) : receipts.length === 0 ? (
        <EmptyState text="Нет чеков за выбранный период" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[70px]">№</TableHead>
                <TableHead>Дата</TableHead>
                <TableHead>Закрытие</TableHead>
                <TableHead>Подразделение</TableHead>
                <TableHead>Официант</TableHead>
                <TableHead className="text-center">Гостей</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead className="text-right">Скидка</TableHead>
                <TableHead className="text-center">Позиций</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {receipts.map((r) => (
                <TableRow
                  key={`${r.id}-${r.open_date}`}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => { setSelectedId(r.id); setSelectedDate(r.open_date) }}
                >
                  <TableCell className="font-mono text-xs tabular">{r.order_num}</TableCell>
                  <TableCell className="text-sm">{formatDate(r.open_date)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {new Date(r.close_time).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                  </TableCell>
                  <TableCell className="text-sm">{r.department_name || '—'}</TableCell>
                  <TableCell className="text-sm">{r.waiter_name || '—'}</TableCell>
                  <TableCell className="text-center tabular">{r.guest_num ?? '—'}</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(r.total_sum)}</TableCell>
                  <TableCell className="text-right tabular">
                    {r.discount_sum > 0 ? formatCurrency(r.discount_sum) : '—'}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary">{r.items_count}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Страница {page + 1} · показано {receipts.length}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                ←
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={receipts.length < PAGE_SIZE}
              >
                →
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Receipt detail dialog */}
      <Dialog
        open={selectedId != null}
        onOpenChange={(open) => { if (!open) { setSelectedId(null); setSelectedDate(null) } }}
      >
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ReceiptIcon className="h-5 w-5" />
              Чек #{detail.data?.order_num}
            </DialogTitle>
          </DialogHeader>

          {detail.isLoading ? (
            <LoadingSpinner />
          ) : detail.data ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Дата:</span>{' '}
                  {formatDate(detail.data.open_date)}
                </div>
                <div>
                  <span className="text-muted-foreground">Закрытие:</span>{' '}
                  {formatDateTime(detail.data.close_time)}
                </div>
                <div>
                  <span className="text-muted-foreground">Подразделение:</span>{' '}
                  {detail.data.department_name || '—'}
                </div>
                <div>
                  <span className="text-muted-foreground">Официант:</span>{' '}
                  {detail.data.waiter_name || '—'}
                </div>
                <div>
                  <span className="text-muted-foreground">Тип заказа:</span>{' '}
                  {detail.data.order_type || '—'}
                </div>
                <div>
                  <span className="text-muted-foreground">Стол:</span>{' '}
                  {detail.data.table_num || '—'}
                </div>
                <div>
                  <span className="text-muted-foreground">Гостей:</span>{' '}
                  {detail.data.guest_num ?? '—'}
                </div>
                <div>
                  <span className="text-muted-foreground">Итого:</span>{' '}
                  <b>{formatCurrency(detail.data.total_sum)}</b>
                </div>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Блюдо</TableHead>
                    <TableHead>Группа</TableHead>
                    <TableHead className="text-right">Кол-во</TableHead>
                    <TableHead className="text-right">Цена</TableHead>
                    <TableHead className="text-right">Сумма</TableHead>
                    <TableHead className="text-right">Скидка</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.data.items.map((it) => (
                    <TableRow key={it.id}>
                      <TableCell>
                        <div className="text-sm font-medium">{it.dish_name}</div>
                        {it.dish_code && (
                          <div className="text-xs text-muted-foreground font-mono">{it.dish_code}</div>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{it.dish_group || '—'}</TableCell>
                      <TableCell className="text-right tabular">{it.qty}</TableCell>
                      <TableCell className="text-right tabular">
                        {it.price_per_unit != null ? formatCurrency(it.price_per_unit) : '—'}
                      </TableCell>
                      <TableCell className="text-right tabular">{formatCurrency(it.dish_sum)}</TableCell>
                      <TableCell className="text-right tabular">
                        {it.discount_sum > 0 ? formatCurrency(it.discount_sum) : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
