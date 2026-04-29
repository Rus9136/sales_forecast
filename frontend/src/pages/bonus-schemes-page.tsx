import { useState } from 'react'
import { useBonusSchemes, useBonusPositions } from '@/hooks/use-bonus'
import { useDepartments } from '@/hooks/use-departments'
import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const MODEL_LABELS: Record<string, string> = {
  flat_by_kpi: 'Фикс. сумма по KPI',
  revenue_percent_by_kpi: '% от выручки × KPI',
  revenue_direct: 'Прямой % от выручки',
  combined_products: 'Комбинированный (продукты)',
  team_revenue_by_kpi: 'Командный (KITCHEN)',
}

export function BonusSchemesPage() {
  const [departmentId, setDepartmentId] = useState<string>('__all__')
  const [openSchemeId, setOpenSchemeId] = useState<number | null>(null)

  const filterDept = departmentId === '__all__' ? undefined : departmentId
  const { data: schemes = [], isLoading, error } = useBonusSchemes({ department_id: filterDept })
  const { data: positions = [] } = useBonusPositions()
  const { data: departments = [] } = useDepartments(true)

  const positionMap = Object.fromEntries(positions.map((p) => [p.id, p]))
  const departmentMap = Object.fromEntries(departments.map((d) => [d.id, d]))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Схемы расчёта бонусов</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Фильтры</CardTitle>
        </CardHeader>
        <CardContent>
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
        </CardContent>
      </Card>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorAlert message={(error as Error).message} />}

      {!isLoading && !error && schemes.length === 0 && (
        <EmptyState text="Схемы не найдены" />
      )}

      {schemes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Схемы ({schemes.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Локация</TableHead>
                  <TableHead>Должность / Команда</TableHead>
                  <TableHead>Модель</TableHead>
                  <TableHead>Версия</TableHead>
                  <TableHead>Действует с</TableHead>
                  <TableHead>Действует по</TableHead>
                  <TableHead>Конфиг</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schemes.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{departmentMap[s.department_id]?.name ?? s.department_id.slice(0, 8) + '…'}</TableCell>
                    <TableCell>
                      {s.position_id != null
                        ? positionMap[s.position_id]?.name ?? `position #${s.position_id}`
                        : <Badge variant="secondary">team #{s.team_id}</Badge>}
                    </TableCell>
                    <TableCell><Badge variant="outline">{MODEL_LABELS[s.calculation_model] ?? s.calculation_model}</Badge></TableCell>
                    <TableCell>v{s.version}</TableCell>
                    <TableCell>{s.effective_from ?? '—'}</TableCell>
                    <TableCell>{s.effective_to ?? <Badge>активна</Badge>}</TableCell>
                    <TableCell>
                      <button
                        className="text-blue-600 hover:underline text-sm"
                        onClick={() => setOpenSchemeId(s.id)}
                      >
                        Показать
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={openSchemeId != null} onOpenChange={(o) => !o && setOpenSchemeId(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Конфиг схемы #{openSchemeId}</DialogTitle>
          </DialogHeader>
          {openSchemeId && (
            <pre className="text-xs bg-muted p-4 rounded overflow-x-auto">
              {JSON.stringify(schemes.find((s) => s.id === openSchemeId)?.config ?? {}, null, 2)}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
