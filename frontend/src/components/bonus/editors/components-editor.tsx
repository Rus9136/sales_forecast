import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Trash2, Plus } from 'lucide-react'
import { RevenueSourceSelect } from './revenue-source-select'

export interface ComponentRow {
  code: string
  name: string
  source: string
  /** Stored as fraction (0.001 = 0.1%). UI shows percent. */
  rate: string
}

interface Props {
  value: ComponentRow[]
  onChange: (rows: ComponentRow[]) => void
}

export function ComponentsEditor({ value, onChange }: Props) {
  const update = (idx: number, patch: Partial<ComponentRow>) => {
    onChange(value.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }
  const remove = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx))
  }
  const add = () => {
    onChange([
      ...value,
      { code: '', name: '', source: '', rate: '0' },
    ])
  }
  return (
    <div className="space-y-2">
      {value.length === 0 ? (
        <div className="border border-dashed rounded-md p-4 text-center text-sm text-muted-foreground">
          Компоненты не добавлены. Добавьте источники и их ставки.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[15%]">Код</TableHead>
              <TableHead className="w-[20%]">Название</TableHead>
              <TableHead className="w-[40%]">Источник</TableHead>
              <TableHead className="w-[20%]">Ставка (%)</TableHead>
              <TableHead className="w-[5%]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {value.map((row, idx) => (
              <TableRow key={idx}>
                <TableCell>
                  <Input
                    value={row.code}
                    onChange={(e) => update(idx, { code: e.target.value })}
                    placeholder="ready_products"
                  />
                </TableCell>
                <TableCell>
                  <Input
                    value={row.name}
                    onChange={(e) => update(idx, { name: e.target.value })}
                    placeholder="Готовая продукция"
                  />
                </TableCell>
                <TableCell>
                  <RevenueSourceSelect
                    value={row.source}
                    onChange={(v) => update(idx, { source: v })}
                    valueTypes={['revenue']}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={0}
                    step={0.01}
                    value={fractionToPercent(row.rate)}
                    onChange={(e) =>
                      update(idx, { rate: percentToFraction(e.target.value) })
                    }
                  />
                  <span className="text-[10px] text-muted-foreground">
                    Хранится как доля: {row.rate}
                  </span>
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(idx)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Button type="button" variant="outline" size="sm" onClick={add}>
        <Plus className="h-4 w-4 mr-1" /> Добавить компонент
      </Button>
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
