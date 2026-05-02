import { useDataSources, useCalculationModels, useBonusKpiDefinitions } from '@/hooks/use-bonus'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Alert, AlertDescription } from '@/components/ui/alert'
import type { CalculationModel, DataSourceInfo, CalculationModelInfo } from '@/types/bonus'

interface KpiBlock {
  code: string
  source: string
  direction: 'higher_is_better' | 'lower_is_better' | 'binary'
  target?: string | number | null
  target_metric?: string | null
  cap_at_100?: boolean
  weight?: string | number
}

interface FlatGrade {
  from: number | string
  to: number | string
  value: string | number
}

interface RateGrade {
  from: number | string
  to: number | string
  rate: string | number
}

interface ProductComponent {
  code: string
  name: string
  source: string
  rate: string | number
}

interface SchemeConfigShape {
  model?: string
  kpis?: KpiBlock[]
  grades?: Array<FlatGrade | RateGrade>
  revenue_source?: string
  rate?: string | number
  components?: ProductComponent[]
  apply_shifts_proration?: boolean
  shifts_proration_formula?: string
  only_worked_days?: boolean
  below_threshold_bonus?: string | number
  below_threshold_bonus_zero?: boolean
  distribution_formula?: string
  exclude_probation_period?: boolean
  exclude_violators?: boolean
  require_no_violations?: boolean
}

interface Props {
  model: CalculationModel
  config: SchemeConfigShape
}

const DIRECTION_LABEL: Record<string, string> = {
  higher_is_better: 'Чем выше, тем лучше',
  lower_is_better: 'Чем ниже, тем лучше',
  binary: 'Бинарный (есть/нет)',
}

const DIRECTION_BADGE: Record<string, 'default' | 'secondary' | 'outline'> = {
  higher_is_better: 'default',
  lower_is_better: 'secondary',
  binary: 'outline',
}

const CATEGORY_LABEL: Record<string, string> = {
  iiko_location: 'iiko (локация)',
  iiko_personal: 'iiko (личная)',
  iiko_plan: 'iiko (план)',
  iiko_products: 'iiko (продукты)',
  manual: 'Ручной ввод',
  crm: 'CRM',
  hr: 'HR',
  tco: 'TCO (смены)',
}

function formatMoney(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'string' ? Number(v) : v
  return Number.isFinite(n) ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : String(v)
}

function formatRate(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'string' ? Number(v) : v
  if (!Number.isFinite(n)) return String(v)
  // 0.045 → 4.5%, 0.0007 → 0.07%
  const pct = n * 100
  return pct.toFixed(pct < 1 ? 3 : 2) + '%'
}

function SourceBadge({
  code,
  sources,
}: {
  code: string
  sources: DataSourceInfo[]
}) {
  const src = sources.find((s) => s.code === code)
  if (!src) {
    return (
      <span className="font-mono text-xs text-muted-foreground" title={code}>
        {code}
      </span>
    )
  }
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1">
        <span className="text-sm font-medium">{src.name}</span>
        {src.is_stub && (
          <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">
            заглушка
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{CATEGORY_LABEL[src.category] ?? src.category}</span>
        {src.unit && <span>· {src.unit}</span>}
        <code className="text-[10px] opacity-60">{code}</code>
      </div>
    </div>
  )
}

function KpiTable({
  kpis,
  sources,
  kpiDefs,
}: {
  kpis: KpiBlock[]
  sources: DataSourceInfo[]
  kpiDefs: Array<{ code: string; name: string }>
}) {
  const kpiNameByCode = Object.fromEntries(kpiDefs.map((k) => [k.code, k.name]))
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[30%]">KPI</TableHead>
          <TableHead className="w-[35%]">Источник данных</TableHead>
          <TableHead className="w-[20%]">Направление</TableHead>
          <TableHead className="w-[15%]">Цель</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {kpis.map((k, idx) => (
          <TableRow key={`${k.code}-${idx}`}>
            <TableCell>
              <div className="text-sm font-medium">
                {kpiNameByCode[k.code] ?? k.code}
              </div>
              <code className="text-[10px] text-muted-foreground">{k.code}</code>
            </TableCell>
            <TableCell>
              <SourceBadge code={k.source} sources={sources} />
            </TableCell>
            <TableCell>
              <Badge variant={DIRECTION_BADGE[k.direction] ?? 'outline'}>
                {DIRECTION_LABEL[k.direction] ?? k.direction}
              </Badge>
            </TableCell>
            <TableCell className="text-sm">
              {k.target != null ? String(k.target) : k.target_metric ?? '—'}
              {k.target_metric && (
                <div className="text-[10px] text-muted-foreground" title="из bonus_monthly_plan">
                  {k.target_metric}
                </div>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function FlatGradesTable({ grades }: { grades: FlatGrade[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>От %</TableHead>
          <TableHead>До %</TableHead>
          <TableHead className="text-right">Сумма бонуса</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grades.map((g, idx) => (
          <TableRow key={idx}>
            <TableCell>{g.from}%</TableCell>
            <TableCell>{g.to}%</TableCell>
            <TableCell className="text-right font-medium">{formatMoney(g.value)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function RateGradesTable({ grades }: { grades: RateGrade[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>От %</TableHead>
          <TableHead>До %</TableHead>
          <TableHead className="text-right">Ставка от выручки</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grades.map((g, idx) => (
          <TableRow key={idx}>
            <TableCell>{g.from}%</TableCell>
            <TableCell>{g.to}%</TableCell>
            <TableCell className="text-right font-medium">{formatRate(g.rate)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function ComponentsTable({
  components,
  sources,
}: {
  components: ProductComponent[]
  sources: DataSourceInfo[]
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Компонент</TableHead>
          <TableHead>Источник</TableHead>
          <TableHead className="text-right">Ставка</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {components.map((c) => (
          <TableRow key={c.code}>
            <TableCell>
              <div className="text-sm font-medium">{c.name}</div>
              <code className="text-[10px] text-muted-foreground">{c.code}</code>
            </TableCell>
            <TableCell>
              <SourceBadge code={c.source} sources={sources} />
            </TableCell>
            <TableCell className="text-right font-medium">{formatRate(c.rate)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function OptionsList({
  config,
  modelMeta,
}: {
  config: SchemeConfigShape
  modelMeta: CalculationModelInfo | undefined
}) {
  if (!modelMeta) return null
  const items = modelMeta.options.map((opt) => {
    const raw = (config as Record<string, unknown>)[opt.key]
    let display: string
    if (opt.type === 'bool') {
      display = raw === true ? 'Да' : 'Нет'
    } else if (opt.type === 'enum' && opt.options) {
      const found = opt.options.find((o) => o.value === raw)
      display = found?.label ?? String(raw ?? '—')
    } else if (opt.type === 'money') {
      display = formatMoney(raw as string | number)
    } else {
      display = String(raw ?? '—')
    }
    return { ...opt, display, raw }
  })
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map((opt) => (
        <div key={opt.key} className="border rounded-md p-3 bg-muted/30">
          <div className="flex items-start justify-between gap-2">
            <div className="text-sm font-medium">{opt.label}</div>
            <Badge variant="outline" className="text-xs whitespace-nowrap">
              {opt.display}
            </Badge>
          </div>
          {opt.hint && (
            <div className="text-xs text-muted-foreground mt-1">{opt.hint}</div>
          )}
        </div>
      ))}
    </div>
  )
}

function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

export function SchemeConfigView({ model, config }: Props) {
  const { data: sources = [] } = useDataSources()
  const { data: models = [] } = useCalculationModels()
  const { data: kpiDefs = [] } = useBonusKpiDefinitions()

  const modelMeta = models.find((m) => m.code === model)

  return (
    <div className="space-y-6">
      {modelMeta && (
        <Alert>
          <AlertDescription className="space-y-1">
            <div className="font-medium">{modelMeta.name}</div>
            <div className="text-sm text-muted-foreground">{modelMeta.description}</div>
          </AlertDescription>
        </Alert>
      )}

      {modelMeta?.requires_kpis && config.kpis && config.kpis.length > 0 && (
        <Section
          title={`KPI (${config.kpis.length})`}
          hint="Каждый KPI замеряется по своему источнику; общий % — среднее"
        >
          <KpiTable kpis={config.kpis} sources={sources} kpiDefs={kpiDefs} />
        </Section>
      )}

      {modelMeta?.requires_revenue_source && config.revenue_source && (
        <>
          <Separator />
          <Section title="Источник выручки">
            <div className="border rounded-md p-3 bg-muted/30">
              <SourceBadge code={config.revenue_source} sources={sources} />
            </div>
          </Section>
        </>
      )}

      {modelMeta?.requires_rate && config.rate != null && (
        <>
          <Separator />
          <Section title="Фиксированная ставка">
            <div className="border rounded-md p-3 bg-muted/30 text-lg font-semibold">
              {formatRate(config.rate)}
              <span className="text-sm font-normal text-muted-foreground ml-2">
                (raw: {String(config.rate)})
              </span>
            </div>
          </Section>
        </>
      )}

      {modelMeta?.requires_grades && config.grades && config.grades.length > 0 && (
        <>
          <Separator />
          <Section
            title={`Грейды (${config.grades.length} ступеней)`}
            hint={
              modelMeta.grade_type === 'flat'
                ? '% выполнения KPI → фиксированная сумма'
                : '% выполнения KPI → ставка % от выручки'
            }
          >
            {modelMeta.grade_type === 'flat' ? (
              <FlatGradesTable grades={config.grades as FlatGrade[]} />
            ) : (
              <RateGradesTable grades={config.grades as RateGrade[]} />
            )}
          </Section>
        </>
      )}

      {modelMeta?.supports_components && config.components && config.components.length > 0 && (
        <>
          <Separator />
          <Section
            title={`Компоненты (${config.components.length})`}
            hint="Бонус = сумма (выручка_компонента × ставка_компонента)"
          >
            <ComponentsTable components={config.components} sources={sources} />
          </Section>
        </>
      )}

      {modelMeta && modelMeta.options.length > 0 && (
        <>
          <Separator />
          <Section title="Опции">
            <OptionsList config={config} modelMeta={modelMeta} />
          </Section>
        </>
      )}
    </div>
  )
}
