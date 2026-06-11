import { useState } from 'react'
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
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { useAuditLog } from '@/hooks/use-pricing'
import { formatDateTime } from '@/lib/formatters'

const ALL = '__all__'
const PAGE_SIZE = 100

const ENTITY_LABELS: Record<string, string> = {
  recommendation: 'Рекомендация',
  rule: 'Правило',
  menu_role: 'Роль меню',
  baseline: 'База',
  experiment: 'Эксперимент',
}

function entityLabel(t: string): string {
  return ENTITY_LABELS[t] ?? t
}

function detailsSummary(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) return '—'
  return Object.entries(details)
    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' · ')
}

export function PricingAuditPage() {
  const [entityType, setEntityType] = useState(ALL)
  const [deptId, setDeptId] = useState(ALL)
  const [page, setPage] = useState(0)

  const query = useAuditLog({
    entity_type: entityType === ALL ? undefined : entityType,
    department_id: deptId === ALL ? undefined : deptId,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })

  const onFilter = (fn: () => void) => { fn(); setPage(0) }

  const items = query.data?.items ?? []
  const total = query.data?.total ?? 0

  if (query.error) return <ErrorAlert message={(query.error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Журнал действий</h1>
          <span className="sub">Append-only аудит ценообразования (ТЗ п.9.3)</span>
        </div>
        <div className="page__actions">
          <Button variant="outline" onClick={() => query.refetch()}>
            <RotateCcw className="h-4 w-4 mr-2" /> Обновить
          </Button>
        </div>
      </div>

      <Card>
        <div className="p-4 flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Сущность</Label>
            <Select value={entityType} onValueChange={(v) => onFilter(() => setEntityType(v))}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                {Object.entries(ENTITY_LABELS).map(([k, lbl]) => <SelectItem key={k} value={k}>{lbl}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <DepartmentSelect value={deptId} onChange={(v) => onFilter(() => setDeptId(v))} includeInactive />
        </div>
      </Card>

      {query.isLoading ? (
        <LoadingSpinner />
      ) : items.length === 0 ? (
        <EmptyState text="Записей аудита нет под выбранные фильтры" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">Время</TableHead>
                <TableHead>Сущность</TableHead>
                <TableHead>Действие</TableHead>
                <TableHead>Объект</TableHead>
                <TableHead>Кто</TableHead>
                <TableHead>Детали</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm whitespace-nowrap">{formatDateTime(r.created_at)}</TableCell>
                  <TableCell><Badge variant="outline">{entityLabel(r.entity_type)}</Badge></TableCell>
                  <TableCell className="text-sm font-medium">{r.action}</TableCell>
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {r.entity_id ? r.entity_id.slice(0, 12) : '—'}
                  </TableCell>
                  <TableCell className="text-sm">{r.actor ?? '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-md truncate" title={detailsSummary(r.details)}>
                    {detailsSummary(r.details)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Показано {items.length} из {total.toLocaleString('ru-RU')} · стр. {page + 1}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>←</Button>
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={items.length < PAGE_SIZE}>→</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
