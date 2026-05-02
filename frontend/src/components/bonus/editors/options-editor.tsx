import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import type { CalculationModelOption } from '@/types/bonus'

interface Props {
  options: CalculationModelOption[]
  /** Mutable config dict — options write directly into it. */
  values: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}

export function OptionsEditor({ options, values, onChange }: Props) {
  const update = (key: string, val: unknown) => {
    onChange({ ...values, [key]: val })
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {options.map((opt) => (
        <div key={opt.key} className="border rounded-md p-3 bg-muted/20 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <Label className="text-sm font-medium">{opt.label}</Label>
              {opt.hint && (
                <p className="text-xs text-muted-foreground mt-0.5">{opt.hint}</p>
              )}
            </div>
            {opt.type === 'bool' && (
              <Switch
                checked={Boolean(values[opt.key] ?? opt.default)}
                onCheckedChange={(v) => update(opt.key, v)}
              />
            )}
          </div>

          {opt.type === 'enum' && opt.options && (
            <RadioGroup
              value={String(values[opt.key] ?? opt.default ?? '')}
              onValueChange={(v) => update(opt.key, v)}
              className="gap-2"
            >
              {opt.options.map((o) => (
                <div key={o.value} className="flex items-start gap-2">
                  <RadioGroupItem value={o.value} id={`${opt.key}-${o.value}`} className="mt-0.5" />
                  <Label
                    htmlFor={`${opt.key}-${o.value}`}
                    className="text-sm font-normal cursor-pointer leading-snug"
                  >
                    {o.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          )}

          {opt.type === 'money' && (
            <Input
              type="number"
              min={0}
              step={1000}
              value={String(values[opt.key] ?? opt.default ?? '0')}
              onChange={(e) => update(opt.key, e.target.value)}
            />
          )}
        </div>
      ))}
    </div>
  )
}
