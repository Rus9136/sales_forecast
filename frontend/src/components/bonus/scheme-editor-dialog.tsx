import { useEffect, useMemo, useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react'
import { DepartmentSelect } from '@/components/shared/department-select'
import {
  useBonusPositions, useBonusTeams, useCalculationModels,
  useCreateScheme, useValidateScheme,
} from '@/hooks/use-bonus'
import { ApiError } from '@/lib/api-client'
import type {
  BonusScheme, CalculationModel, CalculationModelInfo,
} from '@/types/bonus'
import { KpiEditor, type KpiRow } from './editors/kpi-editor'
import {
  GradesEditor, type FlatGradeRow, type RateGradeRow,
} from './editors/grades-editor'
import { RevenueSourceSelect } from './editors/revenue-source-select'
import {
  ComponentsEditor, type ComponentRow,
} from './editors/components-editor'
import { OptionsEditor } from './editors/options-editor'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When set — pre-fill from this scheme (creates new version). When null — empty form. */
  baseScheme?: BonusScheme | null
}

interface FormState {
  department_id: string
  target_kind: 'position' | 'team'
  position_id: number | null
  team_id: number | null
  calculation_model: CalculationModel | ''
  effective_from: string
  notes: string
  // config blocks
  kpis: KpiRow[]
  grades_flat: FlatGradeRow[]
  grades_rate: RateGradeRow[]
  revenue_source: string
  rate: string
  components: ComponentRow[]
  options: Record<string, unknown>
}

const EMPTY: FormState = {
  department_id: '',
  target_kind: 'position',
  position_id: null,
  team_id: null,
  calculation_model: '',
  effective_from: today(),
  notes: '',
  kpis: [],
  grades_flat: [],
  grades_rate: [],
  revenue_source: '',
  rate: '0',
  components: [],
  options: {},
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function buildConfig(
  state: FormState,
  modelMeta: CalculationModelInfo | undefined,
): Record<string, unknown> {
  if (!modelMeta) return {}
  const cfg: Record<string, unknown> = { model: state.calculation_model }
  if (modelMeta.requires_kpis) {
    cfg.kpis = state.kpis.map((k) => ({
      code: k.code,
      source: k.source,
      direction: k.direction,
      ...(k.target != null && k.target !== '' ? { target: k.target } : {}),
      ...(k.target_metric ? { target_metric: k.target_metric } : {}),
    }))
  }
  if (modelMeta.requires_revenue_source) {
    cfg.revenue_source = state.revenue_source
  }
  if (modelMeta.requires_rate) {
    cfg.rate = state.rate
  }
  if (modelMeta.requires_grades) {
    cfg.grades = modelMeta.grade_type === 'flat'
      ? state.grades_flat
      : state.grades_rate
  }
  if (modelMeta.supports_components) {
    cfg.components = state.components
  }
  for (const opt of modelMeta.options) {
    if (state.options[opt.key] !== undefined) {
      cfg[opt.key] = state.options[opt.key]
    } else if (opt.default !== undefined) {
      cfg[opt.key] = opt.default
    }
  }
  return cfg
}

function fromBaseScheme(base: BonusScheme): FormState {
  const cfg = (base.config ?? {}) as Record<string, unknown>
  const grades = (cfg.grades as Array<Record<string, string>>) ?? []
  const isFlat = grades.length > 0 && 'value' in grades[0]
  const options: Record<string, unknown> = {}
  for (const k of Object.keys(cfg)) {
    if (
      ![
        'model', 'kpis', 'grades', 'revenue_source', 'rate', 'components',
      ].includes(k)
    ) {
      options[k] = cfg[k]
    }
  }
  return {
    department_id: base.department_id,
    target_kind: base.position_id != null ? 'position' : 'team',
    position_id: base.position_id,
    team_id: base.team_id,
    calculation_model: base.calculation_model,
    effective_from: today(),
    notes: '',
    kpis: ((cfg.kpis as KpiRow[]) ?? []).map((k) => ({
      code: k.code,
      source: k.source,
      direction: k.direction,
      target: k.target != null ? String(k.target) : null,
      target_metric: k.target_metric ?? null,
    })),
    grades_flat: isFlat
      ? (grades as Array<Record<string, unknown>>).map((g) => ({
          from: String(g.from ?? ''),
          to: String(g.to ?? ''),
          value: String(g.value ?? '0'),
        }))
      : [],
    grades_rate: !isFlat
      ? (grades as Array<Record<string, unknown>>).map((g) => ({
          from: String(g.from ?? ''),
          to: String(g.to ?? ''),
          rate: String(g.rate ?? '0'),
        }))
      : [],
    revenue_source: (cfg.revenue_source as string) ?? '',
    rate: cfg.rate != null ? String(cfg.rate) : '0',
    components: ((cfg.components as ComponentRow[]) ?? []).map((c) => ({
      ...c, rate: String(c.rate),
    })),
    options,
  }
}

export function SchemeEditorDialog({ open, onOpenChange, baseScheme }: Props) {
  const [state, setState] = useState<FormState>(EMPTY)
  const [validateOk, setValidateOk] = useState(false)
  const [validateError, setValidateError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const { data: positions = [] } = useBonusPositions()
  const { data: teams = [] } = useBonusTeams(state.department_id || undefined)
  const { data: models = [] } = useCalculationModels()

  const modelMeta = models.find((m) => m.code === state.calculation_model)

  const validate = useValidateScheme()
  const create = useCreateScheme()

  // Pre-fill on open
  useEffect(() => {
    if (open) {
      setState(baseScheme ? fromBaseScheme(baseScheme) : EMPTY)
      setValidateOk(false)
      setValidateError(null)
      setSubmitError(null)
    }
  }, [open, baseScheme])

  // Auto-switch target_kind if model is team-only
  useEffect(() => {
    if (modelMeta?.is_team_model && state.target_kind !== 'team') {
      setState((s) => ({ ...s, target_kind: 'team', position_id: null }))
    } else if (modelMeta && !modelMeta.is_team_model && state.target_kind === 'team') {
      setState((s) => ({ ...s, target_kind: 'position', team_id: null }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelMeta?.code])

  const config = useMemo(() => buildConfig(state, modelMeta), [state, modelMeta])

  const canSubmit = Boolean(
    state.department_id &&
    state.calculation_model &&
    state.effective_from &&
    ((state.target_kind === 'position' && state.position_id != null) ||
      (state.target_kind === 'team' && state.team_id != null)),
  )

  const handleValidate = async () => {
    setValidateOk(false)
    setValidateError(null)
    try {
      await validate.mutateAsync({
        calculation_model: state.calculation_model,
        config,
      })
      setValidateOk(true)
    } catch (err) {
      setValidateOk(false)
      setValidateError(err instanceof ApiError ? err.detail : String(err))
    }
  }

  const handleSubmit = async () => {
    setSubmitError(null)
    try {
      await create.mutateAsync({
        department_id: state.department_id,
        position_id: state.target_kind === 'position' ? state.position_id : null,
        team_id: state.target_kind === 'team' ? state.team_id : null,
        calculation_model: state.calculation_model,
        config,
        effective_from: state.effective_from,
        notes: state.notes || null,
      })
      onOpenChange(false)
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : String(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {baseScheme
              ? `Новая версия схемы #${baseScheme.id} (v${baseScheme.version} → v${baseScheme.version + 1})`
              : 'Создать схему расчёта'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-2">
          {/* === STEP 1: CONTEXT === */}
          <section className="space-y-4">
            <h3 className="text-sm font-semibold uppercase text-muted-foreground">
              Контекст
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label>Локация</Label>
                <DepartmentSelect
                  value={state.department_id || '__all__'}
                  onChange={(v) =>
                    setState((s) => ({
                      ...s, department_id: v === '__all__' ? '' : v, team_id: null,
                    }))
                  }
                />
              </div>
              <div>
                <Label>Дата начала действия</Label>
                <Input
                  type="date"
                  value={state.effective_from}
                  onChange={(e) =>
                    setState((s) => ({ ...s, effective_from: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label>Модель расчёта</Label>
                <Select
                  value={state.calculation_model}
                  onValueChange={(v) =>
                    setState((s) => ({ ...s, calculation_model: v as CalculationModel }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите модель…" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m.code} value={m.code}>
                        {m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {modelMeta && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {modelMeta.description}
                  </p>
                )}
              </div>
              <div>
                <Label>
                  {modelMeta?.is_team_model ? 'Команда' : 'Должность'}
                </Label>
                {modelMeta?.is_team_model ? (
                  <Select
                    value={state.team_id != null ? String(state.team_id) : ''}
                    onValueChange={(v) =>
                      setState((s) => ({ ...s, team_id: Number(v) }))
                    }
                    disabled={!state.department_id || teams.length === 0}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={teams.length === 0 ? 'Нет команд для локации' : 'Выберите команду…'} />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.map((t) => (
                        <SelectItem key={t.id} value={String(t.id)}>
                          {t.name} <Badge variant="outline" className="ml-2">{t.code}</Badge>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Select
                    value={state.position_id != null ? String(state.position_id) : ''}
                    onValueChange={(v) =>
                      setState((s) => ({ ...s, position_id: Number(v) }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите должность…" />
                    </SelectTrigger>
                    <SelectContent>
                      {positions.map((p) => (
                        <SelectItem key={p.id} value={String(p.id)}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
            <div>
              <Label>Заметки (необязательно)</Label>
              <Textarea
                value={state.notes}
                onChange={(e) => setState((s) => ({ ...s, notes: e.target.value }))}
                placeholder="Например: Решение совета от 2026-04-25"
                rows={2}
              />
            </div>
          </section>

          {/* === STEP 2: CONFIG BLOCKS === */}
          {modelMeta && (
            <>
              <Separator />
              <section className="space-y-4">
                <h3 className="text-sm font-semibold uppercase text-muted-foreground">
                  Параметры модели «{modelMeta.name}»
                </h3>

                {modelMeta.requires_kpis && (
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">KPI</Label>
                    <p className="text-xs text-muted-foreground">
                      Каждый KPI — свой источник данных. Общий % = среднее по всем KPI.
                    </p>
                    <KpiEditor
                      value={state.kpis}
                      onChange={(rows) => setState((s) => ({ ...s, kpis: rows }))}
                    />
                  </div>
                )}

                {modelMeta.requires_revenue_source && (
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">Источник выручки</Label>
                    <RevenueSourceSelect
                      value={state.revenue_source}
                      onChange={(v) =>
                        setState((s) => ({ ...s, revenue_source: v }))
                      }
                    />
                  </div>
                )}

                {modelMeta.requires_rate && (
                  <div className="space-y-2 max-w-xs">
                    <Label className="text-sm font-semibold">Фиксированная ставка (%)</Label>
                    <Input
                      type="number"
                      min={0}
                      step={0.001}
                      value={fractionToPercent(state.rate)}
                      onChange={(e) =>
                        setState((s) => ({ ...s, rate: percentToFraction(e.target.value) }))
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      Хранится как доля: <code>{state.rate}</code>
                    </p>
                  </div>
                )}

                {modelMeta.requires_grades && (
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">
                      Грейды ({modelMeta.grade_type === 'flat' ? 'фиксированная сумма' : 'ставка %'})
                    </Label>
                    {modelMeta.grade_type === 'flat' ? (
                      <GradesEditor
                        type="flat"
                        value={state.grades_flat}
                        onChange={(rows) => setState((s) => ({ ...s, grades_flat: rows }))}
                      />
                    ) : (
                      <GradesEditor
                        type="rate"
                        value={state.grades_rate}
                        onChange={(rows) => setState((s) => ({ ...s, grades_rate: rows }))}
                      />
                    )}
                  </div>
                )}

                {modelMeta.supports_components && (
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">Компоненты</Label>
                    <p className="text-xs text-muted-foreground">
                      Бонус = Σ (выручка_компонента × ставка_компонента)
                    </p>
                    <ComponentsEditor
                      value={state.components}
                      onChange={(rows) => setState((s) => ({ ...s, components: rows }))}
                    />
                  </div>
                )}

                {modelMeta.options.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">Опции</Label>
                    <OptionsEditor
                      options={modelMeta.options}
                      values={state.options}
                      onChange={(next) => setState((s) => ({ ...s, options: next }))}
                    />
                  </div>
                )}
              </section>
            </>
          )}

          {/* === Validation feedback === */}
          {validateOk && (
            <Alert>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-700">
                Конфиг валиден — можно сохранять.
              </AlertDescription>
            </Alert>
          )}
          {validateError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-medium mb-1">Ошибка валидации:</div>
                <pre className="text-xs whitespace-pre-wrap">{validateError}</pre>
              </AlertDescription>
            </Alert>
          )}
          {submitError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-medium mb-1">Ошибка сохранения:</div>
                <pre className="text-xs whitespace-pre-wrap">{submitError}</pre>
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handleValidate}
            disabled={!canSubmit || validate.isPending}
          >
            {validate.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
            Проверить
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit || create.isPending}
          >
            {create.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
            {baseScheme ? 'Сохранить как новую версию' : 'Создать схему'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
          >
            Отмена
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
