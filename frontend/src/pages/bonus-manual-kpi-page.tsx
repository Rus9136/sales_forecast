import { useState } from 'react'
import {
  useManualKpi, useUpsertManualKpi, useDeleteManualKpi, useBonusKpiDefinitions,
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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'

export function BonusManualKpiPage() {
  const today = new Date()
  const [departmentId, setDepartmentId] = useState<string>('__all__')
  const [year, setYear] = useState<number>(today.getFullYear())
  const [month, setMonth] = useState<number>(today.getMonth() + 1)

  const filterDept = departmentId === '__all__' ? undefined : departmentId
  const { data: items = [], isLoading, error } =
    useManualKpi({ department_id: filterDept, year, month })
  const { data: definitions = [] } = useBonusKpiDefinitions()
  const { data: departments = [] } = useDepartments(true)
  const departmentMap = Object.fromEntries(departments.map((d) => [d.id, d]))
  const definitionMap = Object.fromEntries(definitions.map((d) => [d.code, d]))

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    department_id: '',
    kpi_code: '',
    period_year: today.getFullYear(),
    period_month: today.getMonth() + 1,
    fact_value: '',
  })
  const upsert = useUpsertManualKpi()
  const del = useDeleteManualKpi()

  function submit() {
    if (!form.department_id || !form.kpi_code || !form.fact_value) return
    upsert.mutate(form, { onSuccess: () => setOpen(false) })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Ручной ввод KPI</h1>
        <Button onClick={() => {
          setForm({ ...form, department_id: filterDept ?? '', period_year: year, period_month: month })
          setOpen(true)
        }}>Добавить / обновить</Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Период и фильтр</CardTitle></CardHeader>
        <CardContent className="flex gap-4 flex-wrap">
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
          <div className="space-y-1">
            <Label className="text-xs">Год</Label>
            <Input type="number" value={year} onChange={(e) => setYear(Number(e.target.value) || today.getFullYear())} className="w-24" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Месяц</Label>
            <Input type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value) || 1)} className="w-24" />
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorAlert message={(error as Error).message} />}

      <Card>
        <CardHeader><CardTitle>Записи ({items.length})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Локация</TableHead>
                <TableHead>KPI</TableHead>
                <TableHead>Период</TableHead>
                <TableHead className="text-right">Факт</TableHead>
                <TableHead>Документ</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{departmentMap[m.department_id]?.name ?? m.department_id.slice(0, 8) + '…'}</TableCell>
                  <TableCell>{definitionMap[m.kpi_code]?.name ?? m.kpi_code}</TableCell>
                  <TableCell>{m.period_year}-{String(m.period_month).padStart(2, '0')}</TableCell>
                  <TableCell className="text-right font-mono">{m.fact_value}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{m.document_ref ?? '—'}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => del.mutate(m.id)}>Удалить</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Ручной KPI</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <DepartmentSelect
              value={form.department_id || '__all__'}
              onChange={(v) => setForm({ ...form, department_id: v === '__all__' ? '' : v })}
              label="Локация"
              showAll={false}
            />
            <div>
              <Label>KPI</Label>
              <Select value={form.kpi_code} onValueChange={(v) => setForm({ ...form, kpi_code: v })}>
                <SelectTrigger><SelectValue placeholder="Выберите KPI…" /></SelectTrigger>
                <SelectContent>
                  {definitions.map((d) => (
                    <SelectItem key={d.code} value={d.code}>{d.name} ({d.code})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3">
              <div>
                <Label>Год</Label>
                <Input type="number" value={form.period_year}
                  onChange={(e) => setForm({ ...form, period_year: Number(e.target.value) })} />
              </div>
              <div>
                <Label>Месяц</Label>
                <Input type="number" min={1} max={12} value={form.period_month}
                  onChange={(e) => setForm({ ...form, period_month: Number(e.target.value) })} />
              </div>
              <div className="flex-1">
                <Label>Значение</Label>
                <Input value={form.fact_value}
                  onChange={(e) => setForm({ ...form, fact_value: e.target.value })} placeholder="например 95.5" />
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
