import { useMemo, useState } from 'react'
import { Plus, Trash2, Info, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { DepartmentSelect } from '@/components/shared/department-select'
import { ProductSearch } from '@/components/shared/product-search'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import {
  usePricingRules, useCreatePricingRule, useUpdatePricingRule, useDeletePricingRule,
} from '@/hooks/use-pricing'
import { useDepartments } from '@/hooks/use-departments'
import { useProduct } from '@/hooks/use-menu'
import type { Product } from '@/types/menu'
import type { PricingRule } from '@/types/pricing'

type RuleKind = 'percent' | 'days' | 'toggle' | 'rounding' | 'portfolio' | 'competitive'

interface RuleMeta {
  label: string
  description: string
  owner: string
  kind: RuleKind
  defaults: Record<string, unknown>
}

// Schema mirrors app/services/pricing_rules_service.py (VALID_RULE_TYPES + validate()).
const RULE_META: Record<string, RuleMeta> = {
  min_margin: {
    label: 'Минимальная маржа',
    description: 'Не опускать GP-маржу позиции ниже порога.',
    owner: 'Финансовый директор', kind: 'percent', defaults: { value: 0.6 },
  },
  max_step: {
    label: 'Максимальный шаг',
    description: 'Ограничение изменения цены за одну итерацию.',
    owner: 'Коммерческий директор', kind: 'percent', defaults: { value: 0.05 },
  },
  min_frequency: {
    label: 'Минимальная частота',
    description: 'Не менять цену чаще, чем раз в N дней.',
    owner: 'Коммерческий директор', kind: 'days', defaults: { days: 14 },
  },
  no_decrease_anchor: {
    label: 'Якоря только вверх',
    description: 'Запрет снижения цен премиум-якорей.',
    owner: 'Управляющий', kind: 'toggle', defaults: { enabled: true },
  },
  rounding: {
    label: 'Округление цен',
    description: 'Кратность цены; флагманы (премиум/имидж) — отдельный шаг.',
    owner: 'Коммерческий директор', kind: 'rounding', defaults: { step: 50, flagship_step: 100 },
  },
  no_psychological: {
    label: 'Без «психологических» окончаний',
    description: 'Запрет окончаний 9 / 99 на флагманах.',
    owner: 'Коммерческий директор', kind: 'toggle', defaults: { enabled: true, endings: [9, 99] },
  },
  stop_list: {
    label: 'Стоп-лист',
    description: 'Цена позиции/точки не меняется. Обычно scope = позиция или подразделение.',
    owner: 'Управляющий', kind: 'toggle', defaults: { enabled: true },
  },
  max_changes_per_cycle: {
    label: 'Лимит изменений за цикл',
    description: 'Не более N утверждённых изменений на точку за окно дней (портфельное правило).',
    owner: 'Коммерческий директор', kind: 'portfolio', defaults: { value: 15, window_days: 14 },
  },
  min_competitive_idx: {
    label: 'Мин. конкурентный индекс',
    description: 'Цена не ниже k×медианы рынка. Заработает, когда появятся данные о ценах конкурентов — пока не используется.',
    owner: 'Коммерческий директор', kind: 'competitive', defaults: { value: 1.0 },
  },
}

/** Правило одной человеческой фразой — с текущими параметрами. */
function humanSummary(ruleType: string, p: Record<string, unknown>): string {
  const num = (v: unknown, d: number) => (typeof v === 'number' && Number.isFinite(v) ? v : d)
  switch (ruleType) {
    case 'min_margin':
      return `Не предлагать цены, при которых маржа блюда падает ниже ${(num(p.value, 0.6) * 100).toFixed(0)}%.`
    case 'max_step':
      return `Цена меняется не больше чем на ${(num(p.value, 0.05) * 100).toFixed(0)}% за один раз (и не больше +15% суммарно за 90 дней).`
    case 'min_frequency':
      return `Цена одного блюда меняется не чаще, чем раз в ${num(p.days, 14)} дней.`
    case 'no_decrease_anchor':
      return 'Цены премиум-якорей не снижаются — только рост или без изменений.'
    case 'rounding':
      return `Обычные блюда округляются до ${num(p.step, 50)} ₸, якоря и имиджевые — до ${num(p.flagship_step, 100)} ₸.`
    case 'no_psychological':
      return 'На флагманах запрещены «психологические» окончания цен (…9, …99).'
    case 'stop_list':
      return 'Цена не меняется вообще — блюдо или точка исключены из оптимизации.'
    case 'max_changes_per_cycle':
      return `Не больше ${num(p.value, 15)} изменений цен на точку за ${num(p.window_days, 14)} дней.`
    case 'min_competitive_idx':
      return `Цена не ниже ${num(p.value, 1)}× медианы рынка (ждёт данных о конкурентах).`
    default:
      return ''
  }
}

const GLOBAL_ORDER = [
  'min_margin', 'max_step', 'min_frequency', 'no_decrease_anchor',
  'rounding', 'no_psychological', 'max_changes_per_cycle', 'min_competitive_idx',
]

const SCOPE_LABELS: Record<string, string> = {
  global: 'Глобально', segment: 'Сегмент', department: 'Подразделение', product: 'Позиция',
}

function ruleTypeLabel(t: string): string {
  return RULE_META[t]?.label ?? t
}

function paramsSummary(rule: PricingRule): string {
  const p = rule.params as Record<string, number | boolean>
  const meta = RULE_META[rule.rule_type]
  switch (meta?.kind) {
    case 'percent': return `${((Number(p.value) || 0) * 100).toFixed(1)}%`
    case 'days': return `${p.days ?? '—'} дн.`
    case 'toggle': return p.enabled === false ? 'выкл.' : 'вкл.'
    case 'rounding': return `${p.step ?? 50}₸ / ${p.flagship_step ?? 100}₸`
    case 'portfolio': return `${p.value ?? 15} / ${p.window_days ?? 14} дн.`
    case 'competitive': return `k ≥ ${p.value ?? 1}`
    default: return JSON.stringify(p)
  }
}

// ── Guided params editor (shared by cards + create dialog) ─────────
function ParamsEditor({
  ruleType, value, onChange,
}: {
  ruleType: string
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const meta = RULE_META[ruleType]
  if (!meta) return null
  const set = (patch: Record<string, unknown>) => onChange({ ...value, ...patch })

  switch (meta.kind) {
    case 'percent': {
      const pct = Math.round((Number(value.value ?? 0)) * 1000) / 10
      return (
        <div className="flex items-center gap-2">
          <Input
            type="number" step={0.5} min={0} max={100} className="w-24 h-8 tabular"
            value={Number.isFinite(pct) ? pct : ''}
            onChange={(e) => set({ value: (Number(e.target.value) || 0) / 100 })}
          />
          <span className="text-sm text-muted-foreground">%</span>
        </div>
      )
    }
    case 'days':
      return (
        <div className="flex items-center gap-2">
          <Input
            type="number" step={1} min={1} className="w-24 h-8 tabular"
            value={Number(value.days ?? 14)}
            onChange={(e) => set({ days: Number(e.target.value) || 0 })}
          />
          <span className="text-sm text-muted-foreground">дней</span>
        </div>
      )
    case 'toggle':
      return (
        <div className="flex items-center gap-2">
          <Switch
            checked={value.enabled !== false}
            onCheckedChange={(c) => set({ enabled: c })}
          />
          <span className="text-sm text-muted-foreground">
            {value.enabled !== false ? 'включено' : 'выключено'}
          </span>
        </div>
      )
    case 'rounding':
      return (
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Шаг, ₸</Label>
            <Input
              type="number" step={10} min={1} className="w-24 h-8 tabular"
              value={Number(value.step ?? 50)}
              onChange={(e) => set({ step: Number(e.target.value) || 0 })}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Флагманы, ₸</Label>
            <Input
              type="number" step={10} min={1} className="w-24 h-8 tabular"
              value={Number(value.flagship_step ?? 100)}
              onChange={(e) => set({ flagship_step: Number(e.target.value) || 0 })}
            />
          </div>
        </div>
      )
    case 'portfolio':
      return (
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Лимит изменений</Label>
            <Input
              type="number" step={1} min={1} className="w-24 h-8 tabular"
              value={Number(value.value ?? 15)}
              onChange={(e) => set({ value: Number(e.target.value) || 0 })}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Окно, дней</Label>
            <Input
              type="number" step={1} min={1} className="w-24 h-8 tabular"
              value={Number(value.window_days ?? 14)}
              onChange={(e) => set({ window_days: Number(e.target.value) || 0 })}
            />
          </div>
        </div>
      )
    case 'competitive':
      return (
        <div className="flex items-center gap-2">
          <Input
            type="number" step={0.05} min={0} className="w-24 h-8 tabular"
            value={Number(value.value ?? 1)}
            onChange={(e) => set({ value: Number(e.target.value) || 0 })}
          />
          <span className="text-sm text-muted-foreground">× медианы</span>
        </div>
      )
  }
}

// ── Card for a single global rule ──────────────────────────────────
function GlobalRuleCard({ ruleType, rule }: { ruleType: string; rule: PricingRule | null }) {
  const meta = RULE_META[ruleType]
  const create = useCreatePricingRule()
  const update = useUpdatePricingRule()
  const [draft, setDraft] = useState<Record<string, unknown>>(
    () => (rule ? { ...rule.params } : { ...meta.defaults }),
  )

  const dirty = useMemo(
    () => (rule ? JSON.stringify(draft) !== JSON.stringify(rule.params) : true),
    [draft, rule],
  )
  const busy = create.isPending || update.isPending

  const onSave = () => {
    if (rule) update.mutate({ id: rule.id, params: draft })
    else create.mutate({ ruleType, scopeType: 'global', params: draft, configuredByRole: meta.owner })
  }

  return (
    <div className="card">
      <div className="card__header">
        <div>
          <div className="card__title">{meta.label}</div>
          <div className="card__sub">{meta.description}</div>
        </div>
        {rule && (
          <Switch
            checked={rule.is_active}
            onCheckedChange={(c) => update.mutate({ id: rule.id, isActive: c })}
            disabled={busy}
            title={rule.is_active ? 'Правило активно' : 'Правило выключено'}
          />
        )}
      </div>
      <div style={{ padding: '14px 16px' }} className="space-y-3">
        <p className="text-sm" style={{ margin: 0, color: 'var(--text-muted)' }}>
          {humanSummary(ruleType, draft)}
        </p>
        <div style={{ opacity: rule && !rule.is_active ? 0.5 : 1 }}>
          <ParamsEditor ruleType={ruleType} value={draft} onChange={setDraft} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline" className="text-[10px]">{meta.owner}</Badge>
          {rule ? (
            <Button size="sm" onClick={onSave} disabled={!dirty || busy}>
              {busy ? 'Сохранение…' : 'Сохранить'}
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={onSave} disabled={busy}>
              <Plus className="h-4 w-4 mr-1" /> Создать
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

const ALL = '__all__'

// ── Create scoped override dialog ──────────────────────────────────
function CreateOverrideDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreatePricingRule()
  const [ruleType, setRuleType] = useState('stop_list')
  const [scopeType, setScopeType] = useState('department')
  const [departmentId, setDepartmentId] = useState(ALL)
  const [product, setProduct] = useState<Product | null>(null)
  const [params, setParams] = useState<Record<string, unknown>>({ ...RULE_META.stop_list.defaults })
  const [error, setError] = useState<string | null>(null)

  const onRuleTypeChange = (t: string) => {
    setRuleType(t)
    setParams({ ...RULE_META[t].defaults })
  }

  const scopeId = scopeType === 'department'
    ? (departmentId === ALL ? '' : departmentId)
    : scopeType === 'product' ? (product ? String(product.id) : '') : ''

  const onCreate = () => {
    setError(null)
    if ((scopeType === 'department' || scopeType === 'product') && !scopeId) {
      setError(scopeType === 'department' ? 'Выберите подразделение' : 'Найдите и выберите блюдо')
      return
    }
    create.mutate(
      { ruleType, scopeType, scopeId: scopeId || undefined, params, configuredByRole: RULE_META[ruleType].owner },
      {
        onSuccess: () => onOpenChange(false),
        onError: (e) => setError((e as Error).message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Переопределение правила</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs">Тип правила</Label>
            <Select value={ruleType} onValueChange={onRuleTypeChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.keys(RULE_META).map((t) => (
                  <SelectItem key={t} value={t}>{RULE_META[t].label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Уровень (scope)</Label>
            <Select value={scopeType} onValueChange={setScopeType}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="department">Подразделение</SelectItem>
                <SelectItem value="product">Позиция</SelectItem>
                <SelectItem value="global">Глобально</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {scopeType === 'department' && (
            <div className="space-y-1">
              <Label className="text-xs">Подразделение</Label>
              <DepartmentSelect value={departmentId} onChange={setDepartmentId} includeInactive />
            </div>
          )}
          {scopeType === 'product' && (
            <div className="space-y-1">
              <Label className="text-xs">Блюдо</Label>
              <ProductSearch value={product} onChange={setProduct} />
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs">Параметры</Label>
            <ParamsEditor ruleType={ruleType} value={params} onChange={setParams} />
          </div>
          {error && <ErrorAlert message={error} />}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Отмена</Button>
          <Button onClick={onCreate} disabled={create.isPending}>
            {create.isPending ? 'Создание…' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function PricingRulesPage() {
  const rulesQuery = usePricingRules()
  const update = useUpdatePricingRule()
  const del = useDeletePricingRule()
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<PricingRule | null>(null)

  const rules = rulesQuery.data?.items ?? []
  const globalByType = useMemo(() => {
    const map = new Map<string, PricingRule>()
    for (const r of rules) {
      if (r.scope_type === 'global' && !r.scope_id) map.set(r.rule_type, r)
    }
    return map
  }, [rules])

  const overrides = useMemo(
    () => rules.filter((r) => !(r.scope_type === 'global' && !r.scope_id)),
    [rules],
  )

  if (rulesQuery.error) return <ErrorAlert message={(rulesQuery.error as Error).message} />

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span className="pricing-hint">
          Правила — рамки, за которые система никогда не выходит, даже если это выгодно.
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button variant="outline" onClick={() => rulesQuery.refetch()}>
            <RotateCcw className="h-4 w-4 mr-2" /> Обновить
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" /> Исключение для блюда / точки
          </Button>
        </div>
      </div>

      <div
        className="flex items-start gap-2 rounded-md p-3 text-sm"
        style={{ background: 'var(--surface-2)', color: 'var(--text-muted)' }}
      >
        <Info size={15} className="mt-0.5 shrink-0" />
        <span>
          Правила ниже действуют для всего меню. Для отдельного блюда или точки можно завести
          исключение — оно сильнее общего правила. Изменения вступают в силу при следующем
          пересчёте предложений (каждую ночь в 05:00). Даже если правило выключить, система
          сохраняет базовые защитные пороги.
        </span>
      </div>

      {rulesQuery.isLoading ? (
        <LoadingSpinner />
      ) : (
        <>
          {/* Global rule cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
            {GLOBAL_ORDER.map((t) => (
              <GlobalRuleCard
                key={`${t}:${globalByType.get(t)?.id ?? 'new'}`}
                ruleType={t}
                rule={globalByType.get(t) ?? null}
              />
            ))}
          </div>

          {/* Scoped overrides */}
          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Исключения</div>
                <div className="card__sub">Правила для отдельных точек и блюд — сильнее общих</div>
              </div>
            </div>
            {overrides.length === 0 ? (
              <div className="p-4 text-sm text-muted-foreground">
                Исключений нет — для всех блюд действуют общие правила выше.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Правило</TableHead>
                    <TableHead>Уровень</TableHead>
                    <TableHead>Для кого</TableHead>
                    <TableHead>Параметры</TableHead>
                    <TableHead className="text-center">Активно</TableHead>
                    <TableHead className="text-right">Действия</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overrides.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="text-sm font-medium">{ruleTypeLabel(r.rule_type)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{SCOPE_LABELS[r.scope_type] ?? r.scope_type}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        <ScopeName scopeType={r.scope_type} scopeId={r.scope_id} />
                      </TableCell>
                      <TableCell className="text-sm tabular">{paramsSummary(r)}</TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={r.is_active}
                          onCheckedChange={(c) => update.mutate({ id: r.id, isActive: c })}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setDeleteTarget(r)}>
                          <Trash2 size={15} style={{ color: 'var(--neg)' }} />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </>
      )}

      <CreateOverrideDialog open={createOpen} onOpenChange={setCreateOpen} />

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null) }}
        title="Удалить правило?"
        description={
          deleteTarget
            ? `${ruleTypeLabel(deleteTarget.rule_type)} · ${SCOPE_LABELS[deleteTarget.scope_type] ?? deleteTarget.scope_type}. Позиция вернётся под глобальное правило.`
            : ''
        }
        confirmText="Удалить"
        destructive
        onConfirm={() => {
          if (deleteTarget) del.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) })
        }}
      />
    </>
  )
}

/** Человекочитаемое имя объекта исключения: точка — по справочнику, блюдо — по каталогу. */
function ScopeName({ scopeType, scopeId }: { scopeType: string; scopeId: string | null }) {
  const { data: departments = [] } = useDepartments(true)
  const isProduct = scopeType === 'product'
  const numericId = isProduct && scopeId ? Number(scopeId) : null
  const product = useProduct(numericId != null && Number.isFinite(numericId) ? numericId : null)

  if (!scopeId) return <span className="text-muted-foreground">—</span>
  if (scopeType === 'department') {
    const dept = departments.find((d) => d.id === scopeId)
    return (
      <span title={scopeId}>
        {dept?.name ?? <span className="font-mono text-xs text-muted-foreground">{scopeId.slice(0, 12)}…</span>}
      </span>
    )
  }
  if (isProduct) {
    return (
      <span title={`product_id ${scopeId}`}>
        {product.data?.name ?? `Блюдо #${scopeId}`}
      </span>
    )
  }
  return <span className="font-mono text-xs text-muted-foreground">{scopeId.slice(0, 12)}</span>
}
