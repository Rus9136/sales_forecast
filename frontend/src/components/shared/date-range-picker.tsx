import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface DateRangePickerProps {
  fromDate: string
  toDate: string
  onFromDateChange: (val: string) => void
  onToDateChange: (val: string) => void
  fromLabel?: string
  toLabel?: string
}

export function DateRangePicker({
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
  fromLabel = 'Дата начала',
  toLabel = 'Дата окончания',
}: DateRangePickerProps) {
  return (
    <div className="flex items-end gap-3">
      <div className="space-y-1">
        <Label className="text-xs">{fromLabel}</Label>
        <Input
          type="date"
          value={fromDate}
          onChange={(e) => onFromDateChange(e.target.value)}
          className="w-40"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">{toLabel}</Label>
        <Input
          type="date"
          value={toDate}
          onChange={(e) => onToDateChange(e.target.value)}
          className="w-40"
        />
      </div>
    </div>
  )
}
