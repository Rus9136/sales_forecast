import { useState } from 'react'
import { useMonthlyPlans, useUpsertMonthlyPlan } from '@/hooks/use-bonus'
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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'

const METRICS: { value: string; label: string }[] = [
  { value: 'sales', label: 'План продаж (тг)' },
  { value: 'profitability', label: 'План рентабельности (%)' },
  { value: 'shifts_norm', label: 'Норма смен' },
]

export function BonusMonthlyPlansPage() {
  const today = new Date()
  const [departmentId, setDepartmentId] = useState<string>('__all__')
  const [year, setYear] = useState<number>(today.getFullYear())
  const filterDept = departmentId === '__all__' ? undefined : departmentId

  const { data: plans = [], isLoading, error } = useMonthlyPlans({ department_id: filterDept, year })
  const { data: departments = [] } = useDepartments(true)
  const departmentMap = Object.fromEntries(departments.map((d) => [d.id, d]))

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    department_id: '',
    metric: 'sales',
    year: today.getFullYear(),
    month: today.getMonth() + 1,
    target_value: '',
  })
  const upsert = useUpsertMonthlyPlan()

  function submit() {
    if (!form.department_id || !form.target_value) return
    upsert.mutate(form, {
      onSuccess: () => setOpen(false),
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Помесячные планы</h1>
        <Button onClick={() => { setForm({ ...form, department_id: filterDept ?? '' }); setOpen(true) }}>
          Добавить / обновить
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Фильтры</CardTitle></CardHeader>
        <CardContent className="flex gap-4">
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
          <div className="space-y-1">
            <Label className="text-xs">Год</Label>
            <Input
              type="number" value={year} onChange={(e) => setYear(Number(e.target.value) || today.getFullYear())}
              className="w-32"
            />
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorAlert message={(error as Error).message} />}

      <Card>
        <CardHeader><CardTitle>Планы ({plans.length})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Локация</TableHead>
                <TableHead>Метрика</TableHead>
                <TableHead>Год</TableHead>
                <TableHead>Месяц</TableHead>
                <TableHead className="text-right">Значение</TableHead>
                <TableHead>Заметки</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plans.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{departmentMap[p.department_id]?.name ?? p.department_id.slice(0, 8) + '…'}</TableCell>
                  <TableCell>{METRICS.find((m) => m.value === p.metric)?.label ?? p.metric}</TableCell>
                  <TableCell>{p.year}</TableCell>
                  <TableCell>{p.month}</TableCell>
                  <TableCell className="text-right font-mono">{p.target_value}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.notes ?? ''}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Помесячный план</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <DepartmentSelect
              value={form.department_id || '__all__'}
              onChange={(v) => setForm({ ...form, department_id: v === '__all__' ? '' : v })}
              label="Локация"
              showAll={false}
            />
            <div>
              <Label>Метрика</Label>
              <Select value={form.metric} onValueChange={(v) => setForm({ ...form, metric: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {METRICS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3">
              <div>
                <Label>Год</Label>
                <Input type="number" value={form.year}
                  onChange={(e) => setForm({ ...form, year: Number(e.target.value) || today.getFullYear() })} />
              </div>
              <div>
                <Label>Месяц</Label>
                <Input type="number" min={1} max={12} value={form.month}
                  onChange={(e) => setForm({ ...form, month: Number(e.target.value) || 1 })} />
              </div>
              <div className="flex-1">
                <Label>Значение</Label>
                <Input value={form.target_value}
                  onChange={(e) => setForm({ ...form, target_value: e.target.value })} placeholder="500000" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Отмена</Button>
            <Button onClick={submit} disabled={upsert.isPending}>Сохранить</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
