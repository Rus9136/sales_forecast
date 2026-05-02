import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Trash2, Plus, AlertTriangle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

export interface FlatGradeRow {
  from: string
  to: string
  value: string
}

export interface RateGradeRow {
  from: string
  to: string
  /** Stored as a fraction (0.045 = 4.5%). UI shows percent. */
  rate: string
}

interface FlatProps {
  type: 'flat'
  value: FlatGradeRow[]
  onChange: (rows: FlatGradeRow[]) => void
}

interface RateProps {
  type: 'rate'
  value: RateGradeRow[]
  onChange: (rows: RateGradeRow[]) => void
}

type Props = FlatProps | RateProps

function validateGrades(
  rows: Array<{ from: string; to: string }>,
): string[] {
  const errors: string[] = []
  for (let i = 0; i < rows.length; i++) {
    const fromN = Number(rows[i].from)
    const toN = Number(rows[i].to)
    if (!Number.isFinite(fromN) || !Number.isFinite(toN)) {
      errors.push(`Ступень ${i + 1}: некорректные числа`)
      continue
    }
    if (fromN > toN) {
      errors.push(`Ступень ${i + 1}: «От» больше «До» (${fromN} > ${toN})`)
    }
    if (i > 0) {
      const prevTo = Number(rows[i - 1].to)
      if (Number.isFinite(prevTo) && fromN <= prevTo) {
        errors.push(`Ступень ${i + 1}: пересекается с предыдущей (${prevTo} ↔ ${fromN})`)
      }
    }
  }
  return errors
}

export function GradesEditor(props: Props) {
  const errors = validateGrades(props.value)

  const addRow = () => {
    const last = props.value[props.value.length - 1]
    const nextFrom = last ? String(Math.min(100, Number(last.to) + 1)) : '70'
    const nextTo = String(Math.min(100, Number(nextFrom) + 9))
    if (props.type === 'flat') {
      props.onChange([
        ...props.value,
        { from: nextFrom, to: nextTo, value: '0' },
      ])
    } else {
      props.onChange([
        ...props.value,
        { from: nextFrom, to: nextTo, rate: '0' },
      ])
    }
  }

  const removeRow = (idx: number) => {
    if (props.type === 'flat') {
      props.onChange(props.value.filter((_, i) => i !== idx))
    } else {
      props.onChange(props.value.filter((_, i) => i !== idx))
    }
  }

  const updateRow = (idx: number, patch: Record<string, string>) => {
    if (props.type === 'flat') {
      props.onChange(
        props.value.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
      )
    } else {
      props.onChange(
        props.value.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
      )
    }
  }

  return (
    <div className="space-y-2">
      {props.value.length === 0 ? (
        <div className="border border-dashed rounded-md p-4 text-center text-sm text-muted-foreground">
          Грейды не заданы. Добавьте хотя бы одну ступень.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[20%]">От %</TableHead>
              <TableHead className="w-[20%]">До %</TableHead>
              <TableHead className="w-[40%]">
                {props.type === 'flat' ? 'Сумма (₸)' : 'Ставка (%)'}
              </TableHead>
              <TableHead className="w-[20%]">Превью</TableHead>
              <TableHead className="w-[5%]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {props.value.map((row, idx) => (
              <TableRow key={idx}>
                <TableCell>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={row.from}
                    onChange={(e) => updateRow(idx, { from: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={row.to}
                    onChange={(e) => updateRow(idx, { to: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  {props.type === 'flat' ? (
                    <Input
                      type="number"
                      min={0}
                      step={1000}
                      value={(row as FlatGradeRow).value}
                      onChange={(e) => updateRow(idx, { value: e.target.value })}
                    />
                  ) : (
                    <Input
                      type="number"
                      min={0}
                      step={0.01}
                      value={fractionToPercent((row as RateGradeRow).rate)}
                      onChange={(e) =>
                        updateRow(idx, { rate: percentToFraction(e.target.value) })
                      }
                    />
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {props.type === 'flat'
                    ? formatMoneyRu((row as FlatGradeRow).value)
                    : formatPct((row as RateGradeRow).rate)}
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRow(idx)}
                    title="Удалить ступень"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <Plus className="h-4 w-4 mr-1" /> Добавить ступень
        </Button>
        {props.type === 'rate' && (
          <span className="text-xs text-muted-foreground">
            Введите процент (например, 4.5). Сохраняется как доля 0.045.
          </span>
        )}
      </div>
      {errors.length > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <ul className="list-disc pl-4 space-y-0.5">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}

function fractionToPercent(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return String(+(n * 100).toFixed(4))
}

function percentToFraction(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return String(+(n / 100).toFixed(6))
}

function formatMoneyRu(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return Math.round(n).toLocaleString('ru-RU') + ' ₸'
}

function formatPct(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  const pct = n * 100
  return pct.toFixed(pct < 1 ? 3 : 2) + '%'
}
