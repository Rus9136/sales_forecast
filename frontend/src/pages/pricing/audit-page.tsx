import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { useAuditLog } from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { formatDateTime } from '@/lib/formatters'
import { auditActionLabel, AUDIT_DETAIL_LABELS } from '@/lib/pricing-labels'

const ALL = '__all__'
const PAGE_SIZE = 100

const ENTITY_LABELS: Record<string, string> = {
  recommendation: 'Рекомендация',
  rule: 'Правило',
  menu_role: 'Роль меню',
  baseline: 'База сравнения',
  experiment: 'Эксперимент',
  rollback: 'Возврат цены',
}

function entityLabel(t: string): string {
  return ENTITY_LABELS[t] ?? t
}

function detailValue(v: unknown): string {
  if (v === true) return 'да'
  if (v === false) return 'нет'
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** details JSONB → читаемая строка «ключ: значение» с локализованными ключами. */
function detailsSummary(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) return '—'
  return Object.entries(details)
    .map(([k, v]) => `${AUDIT_DETAIL_LABELS[k] ?? k}: ${detailValue(v)}`)
    .join(' · ')
}

export function PricingAuditPage() {
  const location = useLocation()
  const { effectiveDepartmentId } = usePricingScope()
  const [entityType, setEntityType] = useState(ALL)
  const [page, setPage] = useState(0)

  const query = useAuditLog({
    entity_type: entityType === ALL ? undefined : entityType,
    department_id: effectiveDepartmentId,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })

  const onFilter = (fn: () => void) => { fn(); setPage(0) }

  const items = query.data?.items ?? []
  const total = query.data?.total ?? 0

  if (query.error) return <ErrorAlert message={(query.error as Error).message} />

  const fromPath = { fromPath: location.pathname + location.search }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span className="pricing-hint">
          Все действия с ценами — кто, что и когда. Записи нельзя изменить или удалить.
        </span>
        <Button variant="outline" style={{ marginLeft: 'auto' }} onClick={() => query.refetch()}>
          <RotateCcw className="h-4 w-4 mr-2" /> Обновить
        </Button>
      </div>

      <Card>
        <div className="p-4 flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Что менялось</Label>
            <Select value={entityType} onValueChange={(v) => onFilter(() => setEntityType(v))}>
              <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                {Object.entries(ENTITY_LABELS).map(([k, lbl]) => <SelectItem key={k} value={k}>{lbl}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {query.isLoading ? (
        <LoadingSpinner />
      ) : items.length === 0 ? (
        <EmptyState text="Записей нет под выбранные фильтры" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">Время</TableHead>
                <TableHead>Что</TableHead>
                <TableHead>Действие</TableHead>
                <TableHead>Кто</TableHead>
                <TableHead>Детали</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm whitespace-nowrap">{formatDateTime(r.created_at)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{entityLabel(r.entity_type)}</Badge>
                    {r.object_label && r.object_product_id != null && r.object_department_id ? (
                      <Link
                        to={`/pricing/position/${r.object_product_id}/${r.object_department_id}`}
                        state={fromPath}
                        className="text-xs font-medium ml-2 hover:underline"
                        style={{ color: 'var(--accent)' }}
                        title="Открыть карточку позиции"
                      >
                        {r.object_label}
                      </Link>
                    ) : r.entity_id ? (
                      <span
                        className="text-xs font-mono text-muted-foreground ml-2"
                        title={r.entity_id}
                      >
                        #{r.entity_id.length > 10 ? r.entity_id.slice(0, 10) + '…' : r.entity_id}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-sm font-medium">{auditActionLabel(r.action)}</TableCell>
                  <TableCell className="text-sm">{r.actor === 'api' ? 'система/API' : (r.actor ?? '—')}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-md truncate" title={detailsSummary(r.details)}>
                    {detailsSummary(r.details)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Всего: {total.toLocaleString('ru-RU')} · стр. {page + 1} из {Math.max(1, Math.ceil(total / PAGE_SIZE))}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>←</Button>
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={(page + 1) * PAGE_SIZE >= total}>→</Button>
            </div>
          </div>
        </Card>
      )}
    </>
  )
}
