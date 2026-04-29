import { useDepartments } from '@/hooks/use-departments'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'

interface DepartmentSelectProps {
  value: string
  onChange: (val: string) => void
  label?: string
  showAll?: boolean
  filterType?: string
}

export function DepartmentSelect({
  value,
  onChange,
  label = 'Подразделение',
  showAll = true,
  filterType = 'DEPARTMENT',
}: DepartmentSelectProps) {
  const { data: departments = [] } = useDepartments(true)

  const filtered = departments
    .filter((d) => (filterType === 'ALL' ? true : d.type === filterType))
    .sort((a, b) => a.name.localeCompare(b.name))

  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-64">
          <SelectValue placeholder="Выберите подразделение" />
        </SelectTrigger>
        <SelectContent>
          {showAll && <SelectItem value="__all__">Все подразделения</SelectItem>}
          {filtered.map((d) => (
            <SelectItem key={d.id} value={d.id}>
              {d.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
