import { useBonusKpiDefinitions } from '@/hooks/use-bonus'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Trash2, Plus } from 'lucide-react'
import { RevenueSourceSelect } from './revenue-source-select'

export interface KpiRow {
  code: string
  source: string
  direction: 'higher_is_better' | 'lower_is_better' | 'binary'
  target?: string | null
  target_metric?: string | null
}

interface Props {
  value: KpiRow[]
  onChange: (rows: KpiRow[]) => void
}

const DIRECTIONS = [
  { value: 'higher_is_better', label: 'Чем выше, тем лучше' },
  { value: 'lower_is_better', label: 'Чем ниже, тем лучше' },
  { value: 'binary', label: 'Бинарный (есть/нет)' },
] as const

const TARGET_METRICS = [
  { value: '', label: '— фиксированная цель —' },
  { value: 'monthly_plan_sales', label: 'monthly_plan_sales (план продаж)' },
  { value: 'monthly_plan_profitability', label: 'monthly_plan_profitability (план рентабельности)' },
]

export function KpiEditor({ value, onChange }: Props) {
  const { data: kpiDefs = [] } = useBonusKpiDefinitions()

  const updateRow = (idx: number, patch: Partial<KpiRow>) => {
    onChange(value.map((row, i) => (i === idx ? { ...row, ...patch } : row)))
  }
  const removeRow = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx))
  }
  const addRow = () => {
    onChange([
      ...value,
      { code: '', source: '', direction: 'higher_is_better', target: '100' },
    ])
  }
  const onPickKpi = (idx: number, kpiCode: string) => {
    const def = kpiDefs.find((k) => k.code === kpiCode)
    if (!def) {
      updateRow(idx, { code: kpiCode })
      return
    }
    updateRow(idx, {
      code: def.code,
      source: def.data_source_code,
      direction: def.direction,
      target: def.default_target ?? value[idx].target,
      target_metric: def.target_metric ?? null,
    })
  }

  return (
    <div className="space-y-2">
      {value.length === 0 ? (
        <div className="border border-dashed rounded-md p-4 text-center text-sm text-muted-foreground">
          KPI не добавлены. Нажмите «Добавить KPI» чтобы начать.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[28%]">KPI</TableHead>
              <TableHead className="w-[28%]">Источник</TableHead>
              <TableHead className="w-[18%]">Направление</TableHead>
              <TableHead className="w-[12%]">Цель</TableHead>
              <TableHead className="w-[10%]">target_metric</TableHead>
              <TableHead className="w-[4%]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {value.map((row, idx) => (
              <TableRow key={idx}>
                <TableCell className="align-top">
                  <Select value={row.code} onValueChange={(v) => onPickKpi(idx, v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      {kpiDefs.map((k) => (
                        <SelectItem key={k.code} value={k.code}>
                          <span className="text-sm">{k.name}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <code className="text-[10px] text-muted-foreground">{row.code || '—'}</code>
                </TableCell>
                <TableCell className="align-top">
                  <RevenueSourceSelect
                    value={row.source}
                    onChange={(v) => updateRow(idx, { source: v })}
                    valueTypes={['kpi_percent', 'kpi_value', 'revenue']}
                  />
                </TableCell>
                <TableCell className="align-top">
                  <Select
                    value={row.direction}
                    onValueChange={(v) =>
                      updateRow(idx, { direction: v as KpiRow['direction'] })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DIRECTIONS.map((d) => (
                        <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="align-top">
                  <Input
                    type="number"
                    step="0.01"
                    value={row.target ?? ''}
                    onChange={(e) => updateRow(idx, { target: e.target.value || null })}
                    placeholder="100"
                  />
                </TableCell>
                <TableCell className="align-top">
                  <Select
                    value={row.target_metric ?? ''}
                    onValueChange={(v) => updateRow(idx, { target_metric: v || null })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TARGET_METRICS.map((m) => (
                        <SelectItem key={m.value || 'none'} value={m.value || '__none__'}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="align-top">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRow(idx)}
                    title="Удалить KPI"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        <Plus className="h-4 w-4 mr-1" /> Добавить KPI
      </Button>
    </div>
  )
}
