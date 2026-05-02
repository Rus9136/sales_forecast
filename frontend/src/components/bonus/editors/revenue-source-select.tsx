import { useDataSources } from '@/hooks/use-bonus'
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel,
  SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import type { DataSourceInfo } from '@/types/bonus'

const CATEGORY_LABEL: Record<string, string> = {
  iiko_location: 'iiko · выручка локации',
  iiko_personal: 'iiko · личная выручка',
  iiko_plan: 'iiko · план продаж',
  iiko_products: 'iiko · продукты (заглушки)',
  manual: 'Ручной ввод',
  crm: 'CRM',
  hr: 'HR',
  tco: 'TCO · смены',
}

const CATEGORY_ORDER = [
  'iiko_personal', 'iiko_location', 'iiko_products', 'iiko_plan',
  'manual', 'crm', 'hr', 'tco',
]

interface Props {
  value: string
  onChange: (code: string) => void
  /** Filter by value_type. Default: 'revenue'. */
  valueTypes?: Array<DataSourceInfo['value_type']>
  placeholder?: string
}

export function RevenueSourceSelect({
  value,
  onChange,
  valueTypes = ['revenue'],
  placeholder = 'Выберите источник…',
}: Props) {
  const { data: sources = [], isLoading } = useDataSources()

  const filtered = sources.filter((s) => valueTypes.includes(s.value_type))
  const groups = new Map<string, DataSourceInfo[]>()
  for (const s of filtered) {
    const key = s.category || 'other'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(s)
  }

  const orderedKeys = [
    ...CATEGORY_ORDER.filter((c) => groups.has(c)),
    ...[...groups.keys()].filter((k) => !CATEGORY_ORDER.includes(k)),
  ]

  const selected = filtered.find((s) => s.code === value)

  return (
    <div className="space-y-1">
      <Select value={value} onValueChange={onChange} disabled={isLoading}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {orderedKeys.map((cat) => (
            <SelectGroup key={cat}>
              <SelectLabel>{CATEGORY_LABEL[cat] ?? cat}</SelectLabel>
              {groups.get(cat)!.map((s) => (
                <SelectItem key={s.code} value={s.code}>
                  <div className="flex items-center gap-2">
                    <span>{s.name}</span>
                    {s.is_stub && (
                      <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300">
                        заглушка
                      </Badge>
                    )}
                    {s.unit && (
                      <span className="text-[10px] text-muted-foreground">{s.unit}</span>
                    )}
                  </div>
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {selected && (
        <p className="text-xs text-muted-foreground">{selected.description}</p>
      )}
    </div>
  )
}
