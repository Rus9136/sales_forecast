import { useState } from 'react'
import { AlertTriangle, Send } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { usePriceOrderPreview, useSendPriceOrder } from '@/hooks/use-pricing'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDate, toISODate } from '@/lib/formatters'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  departmentId?: string
  /** Куда уводим после успешной отправки (вкладка «Приказы»). */
  onSent?: (orderId: number) => void
}

function tomorrow(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return toISODate(d)
}

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

/**
 * Отправка утверждённых цен в iiko приказом.
 *
 * Показывает ровно то, что уедет: позиции, исключённые с причинами и дату
 * вступления в силу. Публикация в боевую кассу — поэтому предпросмотр
 * обязателен, а кнопка называется действием, а не «ОК».
 */
export function SendToIikoDialog({ open, onOpenChange, departmentId, onSent }: Props) {
  const [effectiveDate, setEffectiveDate] = useState(tomorrow())

  const preview = usePriceOrderPreview(
    { departmentId, effectiveDate },
    { enabled: open },
  )
  const sendMut = useSendPriceOrder()

  const data = preview.data
  const draftInIiko = data?.iiko_order_status === 'NEW'

  const send = () => {
    if (!departmentId) return
    sendMut.mutate(
      { departmentId, effectiveDate },
      {
        onSuccess: (res) => {
          onOpenChange(false)
          onSent?.(res.order_id)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Отправить цены в iiko</DialogTitle>
        </DialogHeader>

        {!departmentId ? (
          <p className="text-sm">
            Выберите точку в шапке раздела — приказ создаётся по одной точке.
          </p>
        ) : preview.isLoading ? (
          <LoadingSpinner />
        ) : preview.error ? (
          <ErrorAlert message={apiErrorMessage(preview.error)} title="Не удалось собрать приказ" />
        ) : data ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1">
                <Label className="text-xs">Дата вступления в силу</Label>
                <Input
                  type="date"
                  value={effectiveDate}
                  min={toISODate(new Date())}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-44"
                />
              </div>
              <div className="text-sm">
                <div style={{ color: 'var(--text-muted)' }} className="text-xs">Точка</div>
                <b>{data.department_name}</b>
              </div>
              <div className="text-sm">
                <div style={{ color: 'var(--text-muted)' }} className="text-xs">Ожидаемый эффект</div>
                <b
                  className="tabular"
                  style={{ color: data.total_delta_gp >= 0 ? 'var(--pos)' : 'var(--neg)' }}
                >
                  {data.total_delta_gp > 0 ? '+' : ''}{formatCurrency(data.total_delta_gp)}/нед
                </b>
              </div>
            </div>

            <div
              className="flex items-start gap-2 text-sm"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 12px',
              }}
            >
              <AlertTriangle size={16} style={{ color: 'var(--warn)', flexShrink: 0, marginTop: 2 }} />
              <span>
                {draftInIiko ? (
                  <>
                    Приказ придёт в бэк-офис <b>черновиком</b> — цены в кассе не изменятся, пока
                    приказ не проведут в iiko. Так работает пилотный режим.
                  </>
                ) : (
                  <>
                    Приказ будет <b>проведён сразу</b>: с {formatDate(effectiveDate)} гости увидят
                    новые цены. Отменить можно на вкладке «Приказы».
                  </>
                )}
              </span>
            </div>

            {data.existing_order && (
              <ErrorAlert
                title="На эту дату уже есть приказ"
                message={
                  `Приказ #${data.existing_order.id} (${data.existing_order.status}) занимает ` +
                  'эту дату. Выберите другую дату или отмените его на вкладке «Приказы».'
                }
              />
            )}
            {sendMut.error && (
              <ErrorAlert message={apiErrorMessage(sendMut.error)} title="Приказ не отправлен" />
            )}

            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                Уедет в iiko · {data.n_items}
              </div>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Позиция</TableHead>
                      <TableHead>Цена</TableHead>
                      <TableHead className="text-right">Прибыль/нед</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <TableRow key={item.recommendation_id}>
                        <TableCell className="text-sm">{item.product_name}</TableCell>
                        <TableCell className="tabular text-sm whitespace-nowrap">
                          <span style={{ color: 'var(--text-subtle)', textDecoration: 'line-through' }}>
                            {formatCurrency(item.old_price ?? 0)}
                          </span>
                          <span style={{ color: 'var(--text-subtle)', margin: '0 6px' }}>→</span>
                          <span style={{ fontWeight: 650 }}>{formatCurrency(item.new_price ?? 0)}</span>
                          <span
                            className="tabular text-xs ml-2"
                            style={{ color: (item.delta_pct ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)' }}
                          >
                            {fmtPctSigned(item.delta_pct)}
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular text-sm">
                          {item.delta_gp != null
                            ? `${item.delta_gp > 0 ? '+' : ''}${formatCurrency(item.delta_gp)}`
                            : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {data.excluded.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Не уедет · {data.n_excluded}
                </div>
                <div style={{ maxHeight: 180, overflowY: 'auto' }} className="space-y-1">
                  {data.excluded.map((item) => (
                    <div
                      key={item.recommendation_id}
                      className="text-xs flex items-start gap-2"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {item.product_name}
                      </Badge>
                      <span>{item.reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Отмена</Button>
          <Button
            onClick={send}
            disabled={
              !departmentId || sendMut.isPending || !data?.n_items || !!data?.existing_order
            }
          >
            <Send className="h-4 w-4 mr-2" />
            {sendMut.isPending
              ? 'Отправка…'
              : `Отправить приказ${data?.n_items ? ` · ${data.n_items} поз.` : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
