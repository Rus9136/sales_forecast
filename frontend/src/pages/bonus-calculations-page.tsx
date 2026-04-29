import { useState } from 'react'
import {
  useBonusCalculations, useBonusCalculation, useRunBonusCalculation,
  useApproveCalculation, useRejectCalculation,
} from '@/hooks/use-bonus'
import { useDepartments } from '@/hooks/use-departments'
import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  review: 'На проверке',
  approved: 'Утверждён',
  paid: 'Выплачен',
  rejected: 'Отклонён',
  recalculated: 'Пересчитан',
  superseded: 'Заменён',
}

const STATUS_COLOR: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  draft: 'secondary',
  review: 'outline',
  approved: 'default',
  paid: 'default',
  rejected: 'destructive',
  recalculated: 'outline',
  superseded: 'secondary',
}

export function BonusCalculationsPage() {
  const today = new Date()
  const prev = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const [departmentId, setDepartmentId] = useState<string>('__all__')
  const [year, setYear] = useState<number>(prev.getFullYear())
  const [month, setMonth] = useState<number>(prev.getMonth() + 1)
  const [status, setStatus] = useState<string>('')
  const [openCalcId, setOpenCalcId] = useState<number | null>(null)

  const filterDept = departmentId === '__all__' ? undefined : departmentId

  const { data: calcs = [], isLoading, error } =
    useBonusCalculations({ department_id: filterDept, year, month, status: status || undefined })
  const { data: detail } = useBonusCalculation(openCalcId)
  const { data: departments = [] } = useDepartments(true)
  const departmentMap = Object.fromEntries(departments.map((d) => [d.id, d]))

  const run = useRunBonusCalculation()
  const approve = useApproveCalculation()
  const reject = useRejectCalculation()

  function runForDept() {
    if (!filterDept) return
    run.mutate({ department_id: filterDept, year, month, scope: 'all' })
  }

  const total = calcs.reduce((acc, c) => acc + Number(c.final_bonus), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Расчёты бонусов</h1>
        <div className="flex gap-2">
          <Button onClick={runForDept} disabled={!filterDept || run.isPending}>
            Запустить расчёт за {year}-{String(month).padStart(2, '0')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Фильтры</CardTitle></CardHeader>
        <CardContent className="flex gap-4 flex-wrap">
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
          <div className="space-y-1">
            <Label className="text-xs">Год</Label>
            <Input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-24" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Месяц</Label>
            <Input type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} className="w-24" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Статус</Label>
            <Input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="draft / approved / …" className="w-40" />
          </div>
        </CardContent>
      </Card>

      {run.data && (
        <Card>
          <CardContent className="py-3">
            Запрошено: {run.data.requested}, рассчитано: <strong>{run.data.calculated}</strong>,
            ошибок: {run.data.errors.length}
            {run.data.errors.slice(0, 5).map((e, i) => (
              <div key={i} className="text-xs text-destructive">- {e.employee_id.slice(0, 8)}…: {e.error}</div>
            ))}
          </CardContent>
        </Card>
      )}

      {isLoading && <LoadingSpinner />}
      {error && <ErrorAlert message={(error as Error).message} />}

      <Card>
        <CardHeader>
          <CardTitle>
            Расчёты ({calcs.length}) — итого {total.toLocaleString('ru-RU')} ₸
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Локация</TableHead>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Период</TableHead>
                <TableHead className="text-right">Выручка</TableHead>
                <TableHead className="text-right">KPI %</TableHead>
                <TableHead className="text-right">Ставка</TableHead>
                <TableHead className="text-right">Итого</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {calcs.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.id}</TableCell>
                  <TableCell>{departmentMap[c.department_id]?.name ?? c.department_id.slice(0, 8) + '…'}</TableCell>
                  <TableCell className="font-mono text-xs">{c.employee_id.slice(0, 8)}…</TableCell>
                  <TableCell>{c.period_year}-{String(c.period_month).padStart(2, '0')}</TableCell>
                  <TableCell className="text-right font-mono">{c.revenue_used ?? '—'}</TableCell>
                  <TableCell className="text-right">{c.overall_kpi_percent ?? '—'}</TableCell>
                  <TableCell className="text-right">{c.applied_coefficient ?? '—'}</TableCell>
                  <TableCell className="text-right font-mono font-semibold">{Number(c.final_bonus).toLocaleString('ru-RU')}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_COLOR[c.status] ?? 'secondary'}>
                      {STATUS_LABELS[c.status] ?? c.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => setOpenCalcId(c.id)}>Детали</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={openCalcId != null} onOpenChange={(o) => !o && setOpenCalcId(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Расчёт #{openCalcId}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><Label className="text-xs">Период</Label><div>{detail.period_year}-{String(detail.period_month).padStart(2, '0')}</div></div>
                <div><Label className="text-xs">Статус</Label><div><Badge>{STATUS_LABELS[detail.status] ?? detail.status}</Badge></div></div>
                <div><Label className="text-xs">Schema</Label><div>id={detail.scheme_id}, v{detail.scheme_version}</div></div>
                <div><Label className="text-xs">Final bonus</Label><div className="font-mono font-bold">{Number(detail.final_bonus).toLocaleString('ru-RU')} ₸</div></div>
                <div><Label className="text-xs">Revenue</Label><div className="font-mono">{detail.revenue_used ?? '—'}</div></div>
                <div><Label className="text-xs">KPI overall</Label><div>{detail.overall_kpi_percent ?? '—'}%</div></div>
                <div><Label className="text-xs">Ставка</Label><div>{detail.applied_coefficient ?? '—'}</div></div>
                <div><Label className="text-xs">Смены</Label><div>{detail.shifts_worked}/{detail.shifts_norm}</div></div>
              </div>

              <div>
                <Label className="text-xs">Breakdown шагов</Label>
                <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                  {JSON.stringify(detail.breakdown, null, 2)}
                </pre>
              </div>

              {detail.penalties.length > 0 && (
                <div>
                  <Label className="text-xs">Удержания</Label>
                  <Table>
                    <TableHeader><TableRow>
                      <TableHead>Причина</TableHead><TableHead>%</TableHead>
                      <TableHead className="text-right">Сумма</TableHead>
                    </TableRow></TableHeader>
                    <TableBody>{detail.penalties.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="text-xs">{p.reason_text}</TableCell>
                        <TableCell>{p.penalty_percent ?? '—'}</TableCell>
                        <TableCell className="text-right font-mono">{p.penalty_amount}</TableCell>
                      </TableRow>
                    ))}</TableBody>
                  </Table>
                </div>
              )}

              <div className="flex gap-2 pt-2 border-t">
                {detail.status === 'draft' || detail.status === 'review' ? (
                  <>
                    <Button onClick={() => approve.mutate(detail.id, { onSuccess: () => setOpenCalcId(null) })}>
                      Утвердить
                    </Button>
                    <Button variant="destructive" onClick={() => {
                      const reason = prompt('Причина отклонения?')
                      if (reason) reject.mutate({ id: detail.id, reason },
                        { onSuccess: () => setOpenCalcId(null) })
                    }}>
                      Отклонить
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
