import { useState } from 'react'
import { Link } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Card } from '@/components/ui/card'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import { useElasticityList, useElasticitySummary } from '@/hooks/use-pricing'
import { gradeColor } from '@/lib/pricing-labels'

const ALL = '__all__'
const PAGE_SIZE = 200

const LEVEL_LABELS: Record<string, string> = {
  sku: 'SKU', group: 'Группа', global: 'Глобально',
}

function fmtNum(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('ru-RU')
}

export function PricingElasticityPage() {
  const [deptId, setDeptId] = useState(ALL)
  const [grade, setGrade] = useState(ALL)
  const [level, setLevel] = useState(ALL)
  const [page, setPage] = useState(0)

  const effectiveDept = deptId === ALL ? undefined : deptId
  const summary = useElasticitySummary()
  const list = useElasticityList({
    department_id: effectiveDept,
    reliability_grade: grade === ALL ? undefined : grade,
    estimation_level: level === ALL ? undefined : level,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })

  const onFilter = (fn: () => void) => { fn(); setPage(0) }

  const items = list.data?.items ?? []
  const total = list.data?.total ?? 0
  const s = summary.data
  const reliable = s ? (s.by_grade.A ?? 0) + (s.by_grade.B ?? 0) : null
  const skuLevel = s?.by_level.sku ?? null

  if (list.error) return <ErrorAlert message={(list.error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Эластичность спроса</h1>
          <span className="sub">Оценки ε по чистым каталожным ценам · иерархия SKU → группа → глобально</span>
        </div>
        <div className="page__actions">
          <Button variant="outline" onClick={() => list.refetch()}>
            <RotateCcw className="h-4 w-4 mr-2" /> Обновить
          </Button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <div className="kpi">
          <div className="kpi__label">Всего оценок</div>
          <div className="kpi__value">{fmtNum(s?.total)}</div>
          <div className="kpi__foot"><span style={{ fontSize: 11 }}>SKU × подразделение</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Надёжные (A+B)</div>
          <div className="kpi__value">{fmtNum(reliable)}</div>
          <div className="kpi__foot">
            <span style={{ fontSize: 11 }}>
              {s && reliable != null && s.total ? `${((reliable / s.total) * 100).toFixed(1)}% от всех` : 'грейды A и B'}
            </span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">На уровне SKU</div>
          <div className="kpi__value">{fmtNum(skuLevel)}</div>
          <div className="kpi__foot"><span style={{ fontSize: 11 }}>собственная оценка</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Global prior ε</div>
          <div className="kpi__value">{s?.global_prior != null ? s.global_prior.toFixed(3) : '—'}</div>
          <div className="kpi__foot"><span style={{ fontSize: 11 }}>fallback по всему пулу</span></div>
        </div>
      </div>

      {/* Grade distribution */}
      {s && (
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Распределение по надёжности</div>
              <div className="card__sub">Грейд = число реальных ценовых событий, не значимость</div>
            </div>
          </div>
          <div style={{ padding: '14px 16px', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {(['A', 'B', 'C', 'D'] as const).map((g) => (
              <div key={g} className="flex items-center gap-2">
                <span style={{ color: gradeColor(g), fontWeight: 700, fontSize: 18 }}>{g}</span>
                <span className="tabular text-sm">{fmtNum(s.by_grade[g] ?? 0)}</span>
              </div>
            ))}
            <div style={{ flex: 1 }} />
            {Object.entries(s.by_level).map(([lvl, n]) => (
              <div key={lvl} className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">{LEVEL_LABELS[lvl] ?? lvl}</span>
                <span className="tabular">{fmtNum(n)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <Card>
        <div className="p-4 flex flex-wrap items-end gap-3">
          <DepartmentSelect value={deptId} onChange={(v) => onFilter(() => setDeptId(v))} includeInactive />
          <div className="space-y-1">
            <Label className="text-xs">Надёжность</Label>
            <Select value={grade} onValueChange={(v) => onFilter(() => setGrade(v))}>
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Любая</SelectItem>
                {['A', 'B', 'C', 'D'].map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Уровень</Label>
            <Select value={level} onValueChange={(v) => onFilter(() => setLevel(v))}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Любой</SelectItem>
                {Object.entries(LEVEL_LABELS).map(([k, lbl]) => <SelectItem key={k} value={k}>{lbl}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {list.isLoading ? (
        <LoadingSpinner />
      ) : items.length === 0 ? (
        <EmptyState text="Нет оценок под выбранные фильтры" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Позиция</TableHead>
                <TableHead className="text-right">ε</TableHead>
                <TableHead className="text-right">95% CI</TableHead>
                <TableHead className="text-center">Надёжн.</TableHead>
                <TableHead className="text-center">Уровень</TableHead>
                <TableHead className="text-right">Событий</TableHead>
                <TableHead className="text-right">R²</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={`${r.product_id}:${r.department_id}`}>
                  <TableCell>
                    <Link
                      to={`/pricing/position/${r.product_id}/${r.department_id}`}
                      className="text-sm font-medium hover:underline"
                      style={{ color: 'var(--accent)' }}
                    >
                      {r.product_name ?? `#${r.product_id}`}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular font-medium">{r.elasticity_mean.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular text-muted-foreground">
                    [{r.elasticity_ci_lower.toFixed(2)}; {r.elasticity_ci_upper.toFixed(2)}]
                  </TableCell>
                  <TableCell className="text-center" style={{ color: gradeColor(r.reliability_grade), fontWeight: 600 }}>
                    {r.reliability_grade}
                  </TableCell>
                  <TableCell className="text-center text-sm text-muted-foreground">
                    {LEVEL_LABELS[r.estimation_level] ?? r.estimation_level}
                  </TableCell>
                  <TableCell className="text-right tabular">{r.n_price_events}</TableCell>
                  <TableCell className="text-right tabular text-muted-foreground">
                    {r.model_r_squared != null ? r.model_r_squared.toFixed(2) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Показано {items.length} из {total.toLocaleString('ru-RU')} · стр. {page + 1}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>←</Button>
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={items.length < PAGE_SIZE}>→</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
