import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, RefreshCw, RotateCcw, Undo2 } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import {
  usePriceOrders, usePriceOrder, useCancelPriceOrder, useSyncPriceOrder,
} from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDate, formatDateTime } from '@/lib/formatters'
import {
  iikoDocStatusLabel, orderStatusBadgeVariant, orderStatusLabel,
  statusBadgeVariant, statusLabel,
} from '@/lib/pricing-labels'
import type { PriceOrderListItem } from '@/types/pricing'

const STATUS_CHIPS: { key: string; label: string }[] = [
  { key: '', label: 'Все' },
  { key: 'sent', label: 'Отправленные' },
  { key: 'sending', label: 'Без ответа' },
  { key: 'failed', label: 'С ошибкой' },
  { key: 'cancelled', label: 'Отменённые' },
]

function fmtGp(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${formatCurrency(value)}`
}

export function PricingOrdersPage() {
  const { effectiveDepartmentId } = usePricingScope()
  const [status, setStatus] = useState('')
  const [openOrder, setOpenOrder] = useState<number | null>(null)
  const [cancelTarget, setCancelTarget] = useState<PriceOrderListItem | null>(null)

  const ordersQuery = usePriceOrders({
    department_id: effectiveDepartmentId,
    status: status || undefined,
  })
  const cancelMut = useCancelPriceOrder()
  const syncMut = useSyncPriceOrder()

  const orders = ordersQuery.data?.items ?? []
  const stuck = orders.filter((o) => o.status === 'sending')

  if (ordersQuery.error) return <ErrorAlert message={(ordersQuery.error as Error).message} />

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div className="pricing-chips">
          {STATUS_CHIPS.map((t) => (
            <button
              key={t.key}
              type="button"
              className={'pricing-chip' + (status === t.key ? ' active' : '')}
              onClick={() => setStatus(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <span className="pricing-hint">
        Приказ — документ в iiko, которым цены встают в кассе. Один приказ = одна точка и
        одна дата. Пока цена не появилась в каталоге iiko, предложение остаётся
        «утверждённым»: «Применена» ставится по факту, а не по факту отправки.
      </span>

      {stuck.length > 0 && (
        <Card style={{ borderColor: 'var(--warn)' }}>
          <CardContent className="p-3 text-sm flex items-center gap-2">
            <AlertTriangle size={16} style={{ color: 'var(--warn)' }} />
            <span>
              {stuck.length === 1 ? 'Один приказ ушёл' : `${stuck.length} приказа ушли`} в iiko
              без ответа. Не отправляйте повторно — нажмите «Сверить»: система найдёт документ
              по метке и допишет исход.
            </span>
          </CardContent>
        </Card>
      )}

      {cancelMut.error && (
        <ErrorAlert message={apiErrorMessage(cancelMut.error)} title="Отмена не выполнена" />
      )}
      {syncMut.error && (
        <ErrorAlert message={apiErrorMessage(syncMut.error)} title="Сверка не выполнена" />
      )}
      {cancelMut.data?.method === 'reversed' && (
        <Card>
          <CardContent className="p-3 text-sm">
            Приказ уже действовал, поэтому цены возвращены{' '}
            <b>обратным приказом №{cancelMut.data.reverse_order_id}</b> — он вступает в силу завтра.
          </CardContent>
        </Card>
      )}

      {ordersQuery.isLoading ? (
        <LoadingSpinner />
      ) : orders.length === 0 ? (
        <EmptyState
          text={
            'Приказов пока нет. Утвердите предложения на вкладке «Рекомендации» и нажмите ' +
            '«Отправить в iiko» — цены уедут в кассу одним документом.'
          }
        />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата вступления</TableHead>
                <TableHead>Точка</TableHead>
                <TableHead className="text-center">Документ iiko</TableHead>
                <TableHead className="text-center">Позиций</TableHead>
                <TableHead className="text-right">Ожидаемый эффект</TableHead>
                <TableHead className="text-center">Статус</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((o) => (
                <TableRow key={o.id} className="hover:bg-muted/40">
                  <TableCell className="tabular whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => setOpenOrder(o.id)}
                      className="text-sm font-medium hover:underline"
                      style={{ color: 'var(--accent)' }}
                    >
                      {formatDate(o.effective_date)}
                    </button>
                    <div className="text-xs text-muted-foreground">
                      отправлен {o.sent_at ? formatDateTime(o.sent_at) : '—'}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{o.department_name}</TableCell>
                  <TableCell className="text-center text-sm">
                    {o.iiko_document_number ? (
                      <>
                        <span className="tabular font-medium">№{o.iiko_document_number}</span>
                        <div className="text-xs text-muted-foreground">
                          {iikoDocStatusLabel(o.iiko_status)}
                        </div>
                      </>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-center tabular text-sm">
                    {o.n_items}
                    {o.n_applied > 0 && (
                      <div className="text-xs" style={{ color: 'var(--pos)' }}>
                        {o.n_applied} в кассе
                      </div>
                    )}
                  </TableCell>
                  <TableCell
                    className="text-right tabular"
                    style={{
                      color: (o.total_delta_gp ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)',
                      fontWeight: 600,
                    }}
                  >
                    {fmtGp(o.total_delta_gp)}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant={orderStatusBadgeVariant(o.status)}>
                      {orderStatusLabel(o.status)}
                    </Badge>
                    {o.reverses_order_id && (
                      <div className="text-xs text-muted-foreground mt-1">
                        откат приказа #{o.reverses_order_id}
                      </div>
                    )}
                    {o.error_message && (
                      <div className="text-xs" style={{ color: 'var(--neg)' }}>
                        {o.error_message.slice(0, 90)}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      {(o.status === 'sent' || o.status === 'sending') && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          title="Сверить состояние с iiko"
                          disabled={syncMut.isPending}
                          onClick={() => syncMut.mutate({ orderId: o.id })}
                        >
                          <RefreshCw size={14} />
                        </Button>
                      )}
                      {o.status === 'sent' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          title="Отменить приказ"
                          disabled={cancelMut.isPending}
                          onClick={() => setCancelTarget(o)}
                        >
                          <Undo2 size={14} style={{ color: 'var(--neg)' }} />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <OrderDetailDialog orderId={openOrder} onClose={() => setOpenOrder(null)} />

      <ConfirmDialog
        open={cancelTarget != null}
        onOpenChange={(o) => { if (!o) setCancelTarget(null) }}
        title="Отменить приказ?"
        description={
          cancelTarget && new Date(cancelTarget.effective_date) >= new Date(new Date().toDateString())
            ? `Приказ ещё не вступил в силу — документ №${cancelTarget.iiko_document_number ?? ''} будет удалён в iiko, цены останутся прежними.`
            : 'Приказ уже действует, поэтому iiko не даст его удалить. Система создаст обратный приказ на завтра, который вернёт прежние цены.'
        }
        confirmText="Отменить приказ"
        destructive
        onConfirm={() => {
          if (cancelTarget) cancelMut.mutate({ orderId: cancelTarget.id })
          setCancelTarget(null)
        }}
      />
    </>
  )
}

function OrderDetailDialog({ orderId, onClose }: { orderId: number | null; onClose: () => void }) {
  const query = usePriceOrder(orderId)
  const order = query.data

  return (
    <Dialog open={orderId != null} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            Приказ {order?.iiko_document_number ? `№${order.iiko_document_number}` : `#${orderId}`}
            {order ? ` · ${formatDate(order.effective_date)}` : ''}
          </DialogTitle>
        </DialogHeader>

        {query.isLoading || !order ? (
          <LoadingSpinner />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              <span>Точка <b style={{ color: 'var(--text)' }}>{order.department_name}</b></span>
              <span>
                Состояние{' '}
                <b style={{ color: 'var(--text)' }}>
                  {orderStatusLabel(order.status)} · {iikoDocStatusLabel(order.iiko_status)}
                </b>
              </span>
              <span>
                Отправлен{' '}
                <b style={{ color: 'var(--text)' }}>
                  {order.sent_at ? formatDateTime(order.sent_at) : '—'}
                </b>
              </span>
            </div>

            {order.error_message && (
              <ErrorAlert message={order.error_message} title="Ответ iiko" />
            )}

            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Позиция</TableHead>
                    <TableHead>Цена</TableHead>
                    <TableHead className="text-right">Прибыль/нед</TableHead>
                    <TableHead className="text-center">В кассе</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {order.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="text-sm">
                        <Link
                          to={`/pricing/position/${item.product_id}/${order.department_id}`}
                          className="font-medium hover:underline"
                          style={{ color: 'var(--accent)' }}
                        >
                          {item.product_name ?? `#${item.product_id}`}
                        </Link>
                      </TableCell>
                      <TableCell className="tabular text-sm whitespace-nowrap">
                        <span style={{ color: 'var(--text-subtle)', textDecoration: 'line-through' }}>
                          {formatCurrency(item.old_price ?? 0)}
                        </span>
                        <span style={{ color: 'var(--text-subtle)', margin: '0 6px' }}>→</span>
                        <span style={{ fontWeight: 650 }}>{formatCurrency(item.new_price ?? 0)}</span>
                      </TableCell>
                      <TableCell className="text-right tabular text-sm">
                        {fmtGp(item.delta_gp)}
                      </TableCell>
                      <TableCell className="text-center">
                        {item.recommendation_status ? (
                          <Badge variant={statusBadgeVariant(item.recommendation_status)}>
                            {statusLabel(item.recommendation_status)}
                          </Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">откат</span>
                        )}
                        {item.applied_at && (
                          <div className="text-xs text-muted-foreground">
                            {formatDate(item.applied_at)}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              <RotateCcw size={12} style={{ display: 'inline', marginRight: 4 }} />
              «В кассе» проставляется, когда цена появилась в каталоге iiko с номером этого
              документа — обычно после ночного синка (03:20).
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
