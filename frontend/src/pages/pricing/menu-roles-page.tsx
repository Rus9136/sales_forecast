import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Boxes } from 'lucide-react'

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
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import {
  useMenuRolesList, useMenuRolesSummary, useOverrideMenuRole, useClusterMenuRoles,
} from '@/hooks/use-pricing'
import { apiErrorMessage } from '@/lib/api-client'
import { menuRoleLabel, menuRoleColor, MENU_ROLE_LABELS } from '@/lib/pricing-labels'
import type { SkuMenuRoleItem } from '@/types/pricing'

const ALL = '__all__'
const KEEP_AUTO = '__auto__'
const PAGE_SIZE = 200

const ROLE_ORDER = ['premium_anchor', 'margin_driver', 'traffic_driver', 'tail', 'image_rare']

function featurePct(features: Record<string, unknown> | null, key: string): string {
  if (!features) return '—'
  const v = features[key]
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  return (v * 100).toFixed(1) + '%'
}

export function PricingMenuRolesPage() {
  const [deptId, setDeptId] = useState(ALL)
  const [roleFilter, setRoleFilter] = useState(ALL)
  const [page, setPage] = useState(0)
  const [clusterConfirm, setClusterConfirm] = useState(false)
  const [clusterResult, setClusterResult] = useState<string | null>(null)

  const effectiveDept = deptId === ALL ? undefined : deptId
  const summary = useMenuRolesSummary(effectiveDept)
  const list = useMenuRolesList({
    department_id: effectiveDept,
    effective_role: roleFilter === ALL ? undefined : roleFilter,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })
  const override = useOverrideMenuRole()
  const cluster = useClusterMenuRoles()

  const onFilter = (fn: () => void) => { fn(); setPage(0) }

  const items = list.data?.items ?? []
  const total = list.data?.total ?? 0
  const dist = summary.data?.distribution ?? {}
  const distTotal = summary.data?.total ?? 0
  const maxCount = Math.max(1, ...Object.values(dist))

  const runCluster = () => {
    setClusterResult(null)
    cluster.mutate(
      { lookbackDays: 90 },
      {
        onSuccess: (res) => {
          setClusterResult(`Классифицировано ${res.skus_classified.toLocaleString('ru-RU')} SKU · silhouette ${res.silhouette_score?.toFixed(3) ?? '—'}`)
          setClusterConfirm(false)
        },
      },
    )
  }

  if (list.error) return <ErrorAlert message={(list.error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Роли меню</h1>
          <span className="sub">Кластеризация позиций по 5 ролям (KMeans) + ручное переопределение</span>
        </div>
        <div className="page__actions">
          <Button variant="outline" onClick={() => setClusterConfirm(true)} disabled={cluster.isPending}>
            <Boxes className={`h-4 w-4 mr-2 ${cluster.isPending ? 'animate-pulse' : ''}`} />
            {cluster.isPending ? 'Кластеризация…' : 'Рекластеризация'}
          </Button>
        </div>
      </div>

      {clusterResult && (
        <Card><div className="p-3 text-sm"><span className="font-medium">Готово:</span> {clusterResult}</div></Card>
      )}
      {override.error && <ErrorAlert message={apiErrorMessage(override.error)} title="Не удалось изменить роль" />}

      {/* Distribution */}
      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Распределение ролей</div>
            <div className="card__sub">{distTotal.toLocaleString('ru-RU')} позиций × подразделение</div>
          </div>
        </div>
        <div style={{ padding: '14px 16px' }} className="space-y-2">
          {ROLE_ORDER.map((role) => {
            const count = dist[role] ?? 0
            return (
              <div key={role} className="flex items-center gap-3">
                <span className="text-sm" style={{ width: 140, color: menuRoleColor(role) }}>
                  {menuRoleLabel(role)}
                </span>
                <div style={{ flex: 1, height: 10, background: 'var(--surface-2)', borderRadius: 5, overflow: 'hidden' }}>
                  <div style={{ width: `${(count / maxCount) * 100}%`, height: '100%', background: menuRoleColor(role) }} />
                </div>
                <span className="tabular text-sm" style={{ width: 64, textAlign: 'right' }}>
                  {count.toLocaleString('ru-RU')}
                </span>
                <span className="tabular text-xs text-muted-foreground" style={{ width: 48, textAlign: 'right' }}>
                  {distTotal ? ((count / distTotal) * 100).toFixed(0) + '%' : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="p-4 flex flex-wrap items-end gap-3">
          <DepartmentSelect value={deptId} onChange={(v) => onFilter(() => setDeptId(v))} includeInactive />
          <div className="space-y-1">
            <Label className="text-xs">Роль</Label>
            <Select value={roleFilter} onValueChange={(v) => onFilter(() => setRoleFilter(v))}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все роли</SelectItem>
                {Object.entries(MENU_ROLE_LABELS).map(([k, lbl]) => <SelectItem key={k} value={k}>{lbl}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {list.isLoading ? (
        <LoadingSpinner />
      ) : items.length === 0 ? (
        <EmptyState text="Нет позиций под выбранные фильтры" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Позиция</TableHead>
                <TableHead>Авто-роль</TableHead>
                <TableHead>Эффективная роль</TableHead>
                <TableHead className="text-right">Маржа</TableHead>
                <TableHead className="text-right">Доля выручки</TableHead>
                <TableHead className="text-right">Доля объёма</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <RoleRow
                  key={`${r.product_id}:${r.department_id}`}
                  row={r}
                  busy={override.isPending}
                  onOverride={(manualRole) =>
                    override.mutate({ productId: r.product_id, departmentId: r.department_id, manualRole })
                  }
                />
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

      <ConfirmDialog
        open={clusterConfirm}
        onOpenChange={setClusterConfirm}
        title="Запустить рекластеризацию?"
        description="KMeans пересчитает авто-роли по 90-дневному окну. Ручные переопределения сохраняются. Операция тяжёлая (несколько минут)."
        confirmText="Запустить"
        onConfirm={runCluster}
      />
    </div>
  )
}

function RoleRow({
  row, busy, onOverride,
}: {
  row: SkuMenuRoleItem
  busy: boolean
  onOverride: (manualRole: string) => void
}) {
  return (
    <TableRow>
      <TableCell>
        <Link
          to={`/pricing/position/${row.product_id}/${row.department_id}`}
          className="text-sm font-medium hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          {row.product_name ?? `#${row.product_id}`}
        </Link>
        {row.department_name && (
          <div className="text-xs text-muted-foreground">{row.department_name}</div>
        )}
      </TableCell>
      <TableCell>
        <Badge variant="outline" style={{ color: menuRoleColor(row.auto_role) }}>
          {menuRoleLabel(row.auto_role)}
        </Badge>
      </TableCell>
      <TableCell>
        <Select
          value={row.manual_role ?? KEEP_AUTO}
          onValueChange={(v) => onOverride(v === KEEP_AUTO ? '' : v)}
          disabled={busy}
        >
          <SelectTrigger className="w-44 h-8">
            <SelectValue>
              <span style={{ color: menuRoleColor(row.effective_role) }}>{menuRoleLabel(row.effective_role)}</span>
              {row.manual_role && <span className="text-xs text-muted-foreground"> · ручн.</span>}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={KEEP_AUTO}>Авто ({menuRoleLabel(row.auto_role)})</SelectItem>
            {Object.entries(MENU_ROLE_LABELS).map(([k, lbl]) => <SelectItem key={k} value={k}>{lbl}</SelectItem>)}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="text-right tabular">{featurePct(row.features, 'gp_margin')}</TableCell>
      <TableCell className="text-right tabular">{featurePct(row.features, 'revenue_share')}</TableCell>
      <TableCell className="text-right tabular">{featurePct(row.features, 'qty_share')}</TableCell>
    </TableRow>
  )
}
