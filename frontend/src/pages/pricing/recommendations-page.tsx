import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronDown, ChevronRight, Check, X, Search, Wand2, Download, ArrowUp, ArrowDown,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
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
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { LlmExplanation } from '@/components/shared/llm-explanation'
import {
  useRecommendations, useRecommendationsSummary,
  useReviewRecommendation, useBatchReview, useGenerateRecommendations,
} from '@/hooks/use-pricing'
import { useAuth } from '@/contexts/auth-context'
import { apiDownload } from '@/lib/api-client'
import { formatCurrency } from '@/lib/formatters'
import { menuRoleLabel, statusLabel, gradeColor, MENU_ROLE_LABELS } from '@/lib/pricing-labels'
import type { PriceRecommendation } from '@/types/pricing'

const ALL = '__all__'
const PAGE_SIZE = 200

const STATUS_TABS: { key: string; label: string }[] = [
  { key: 'new', label: 'Новые' },
  { key: 'approved', label: 'Утверждённые' },
  { key: 'rejected', label: 'Отклонённые' },
  { key: '', label: 'Все' },
]

const GRADE_RANK: Record<string, number> = { A: 4, B: 3, C: 2, D: 1 }

type SortKey = 'gp' | 'pct' | 'grade'

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function statusBadgeVariant(s: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (s === 'approved') return 'default'
  if (s === 'rejected') return 'destructive'
  if (s === 'expired') return 'outline'
  return 'secondary'
}

export function PricingRecommendationsPage() {
  const { user } = useAuth()
  const reviewerId = user?.id

  const [departmentId, setDepartmentId] = useState(ALL)
  const [status, setStatus] = useState('new')
  const [roleFilter, setRoleFilter] = useState(ALL)
  const [gradeFilter, setGradeFilter] = useState(ALL)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('gp')
  const [page, setPage] = useState(0)

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [expanded, setExpanded] = useState<number | null>(null)

  // dialogs
  const [rejectTarget, setRejectTarget] = useState<number | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  const [batchConfirm, setBatchConfirm] = useState<'approve' | 'reject' | null>(null)
  const [generateConfirm, setGenerateConfirm] = useState(false)
  const [genResult, setGenResult] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const effectiveDept = departmentId === ALL ? undefined : departmentId

  const recsQuery = useRecommendations({
    department_id: effectiveDept,
    status: status || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })
  const summary = useRecommendationsSummary(effectiveDept)
  const reviewMut = useReviewRecommendation()
  const batchMut = useBatchReview()
  const generateMut = useGenerateRecommendations()

  const items = recsQuery.data?.items ?? []
  const total = recsQuery.data?.total ?? 0

  const filtered = useMemo(() => {
    let rows = items
    if (roleFilter !== ALL) rows = rows.filter((r) => r.menu_role === roleFilter)
    if (gradeFilter !== ALL) rows = rows.filter((r) => r.elasticity_grade === gradeFilter)
    const q = search.trim().toLowerCase()
    if (q) rows = rows.filter((r) => (r.product_name ?? '').toLowerCase().includes(q))
    const sorted = [...rows]
    sorted.sort((a, b) => {
      if (sortKey === 'gp') return (b.delta_gp ?? 0) - (a.delta_gp ?? 0)
      if (sortKey === 'pct') return Math.abs(b.delta_pct ?? 0) - Math.abs(a.delta_pct ?? 0)
      return (GRADE_RANK[b.elasticity_grade ?? ''] ?? 0) - (GRADE_RANK[a.elasticity_grade ?? ''] ?? 0)
    })
    return sorted
  }, [items, roleFilter, gradeFilter, search, sortKey])

  const reviewableOnPage = useMemo(
    () => filtered.filter((r) => r.status === 'new').map((r) => r.id),
    [filtered],
  )
  const allSelected = reviewableOnPage.length > 0 && reviewableOnPage.every((id) => selected.has(id))

  const byStatus = summary.data?.by_status ?? {}
  const potentialGp = summary.data?.total_delta_gp_new ?? null

  const resetSelection = () => setSelected(new Set())

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    setSelected((prev) => {
      if (reviewableOnPage.every((id) => prev.has(id))) return new Set()
      return new Set(reviewableOnPage)
    })
  }

  const selectByGrade = (grade: string) => {
    setSelected(new Set(filtered.filter((r) => r.status === 'new' && r.elasticity_grade === grade).map((r) => r.id)))
  }

  const approveOne = (id: number) =>
    reviewMut.mutate({ id, status: 'approved', reviewerId })

  const confirmReject = () => {
    if (rejectTarget == null) return
    reviewMut.mutate(
      { id: rejectTarget, status: 'rejected', comment: rejectComment.trim() || undefined, reviewerId },
      { onSuccess: () => { setRejectTarget(null); setRejectComment('') } },
    )
  }

  const runBatch = () => {
    if (!batchConfirm) return
    const ids = Array.from(selected)
    batchMut.mutate(
      { ids, status: batchConfirm === 'approve' ? 'approved' : 'rejected', reviewerId },
      { onSuccess: () => { resetSelection(); setBatchConfirm(null) } },
    )
  }

  const runGenerate = () => {
    if (!effectiveDept) return
    generateMut.mutate(
      { departmentId: effectiveDept },
      {
        onSuccess: (res) => {
          setGenResult(`Создано ${res.recommendations_created} рекомендаций из ${res.skus_processed} SKU`)
          setGenerateConfirm(false)
        },
      },
    )
  }

  const handleExport = async () => {
    setExportError(null)
    try {
      const params = new URLSearchParams({ status: status || 'approved' })
      if (effectiveDept) params.set('department_id', effectiveDept)
      const blob = await apiDownload(`/api/pricing-engine/recommendations/export?${params}`)
      const href = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = href
      a.download = `price_recommendations_${status || 'approved'}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(href)
    } catch (e) {
      setExportError((e as Error).message)
    }
  }

  const onFilterChange = (fn: () => void) => { fn(); setPage(0); resetSelection() }

  if (recsQuery.error) return <ErrorAlert message={(recsQuery.error as Error).message} />

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Рекомендации цен</h1>
          <span className="sub">Утверждение и отклонение ценовых предложений оптимизатора</span>
        </div>
        <div className="page__actions">
          <Button
            variant="outline"
            onClick={() => setGenerateConfirm(true)}
            disabled={!effectiveDept || generateMut.isPending}
            title={effectiveDept ? 'Сгенерировать рекомендации для подразделения' : 'Выберите подразделение'}
          >
            <Wand2 className={`h-4 w-4 mr-2 ${generateMut.isPending ? 'animate-spin' : ''}`} />
            {generateMut.isPending ? 'Генерация…' : 'Сгенерировать'}
          </Button>
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4 mr-2" /> Экспорт XLSX
          </Button>
        </div>
      </div>

      {genResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Результат:</span> {genResult}</CardContent></Card>
      )}
      {exportError && <ErrorAlert message={`Экспорт не удался: ${exportError}`} />}

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <DepartmentSelect
              value={departmentId}
              onChange={(v) => onFilterChange(() => setDepartmentId(v))}
              includeInactive
            />
            <div className="space-y-1">
              <Label className="text-xs">Статус</Label>
              <div className="seg">
                {STATUS_TABS.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    className={status === t.key ? 'active' : ''}
                    onClick={() => onFilterChange(() => setStatus(t.key))}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Роль в меню</Label>
              <Select value={roleFilter} onValueChange={(v) => onFilterChange(() => setRoleFilter(v))}>
                <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все роли</SelectItem>
                  {Object.entries(MENU_ROLE_LABELS).map(([key, label]) => (
                    <SelectItem key={key} value={key}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Надёжность ε</Label>
              <Select value={gradeFilter} onValueChange={(v) => onFilterChange(() => setGradeFilter(v))}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Любая</SelectItem>
                  {['A', 'B', 'C', 'D'].map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Сортировка</Label>
              <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="gp">По ΔGP</SelectItem>
                  <SelectItem value="pct">По |Δ%|</SelectItem>
                  <SelectItem value="grade">По надёжности</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Поиск</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Название позиции"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9 w-56"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <div className="kpi">
          <span className="kpi__label">Потенциал ΔGP (новые)</span>
          <span className="kpi__value">{potentialGp != null ? formatCurrency(potentialGp) : '—'}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Новые</span>
          <span className="kpi__value">{(byStatus.new ?? 0).toLocaleString('ru-RU')}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Утверждено</span>
          <span className="kpi__value">{(byStatus.approved ?? 0).toLocaleString('ru-RU')}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Отклонено</span>
          <span className="kpi__value">{(byStatus.rejected ?? 0).toLocaleString('ru-RU')}</span>
        </div>
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <Card>
          <CardContent className="p-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Выбрано: {selected.size}</span>
            <div className="flex-1" />
            <Button size="sm" onClick={() => setBatchConfirm('approve')} disabled={batchMut.isPending}>
              <Check className="h-4 w-4 mr-1" /> Утвердить выбранные
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setBatchConfirm('reject')} disabled={batchMut.isPending}>
              <X className="h-4 w-4 mr-1" /> Отклонить выбранные
            </Button>
            <Button size="sm" variant="ghost" onClick={resetSelection}>Снять выделение</Button>
          </CardContent>
        </Card>
      )}

      {recsQuery.isLoading ? (
        <LoadingSpinner />
      ) : filtered.length === 0 ? (
        <EmptyState text="Нет рекомендаций под выбранные фильтры" />
      ) : (
        <Card>
          {status === 'new' && (
            <div className="flex items-center gap-2 px-3 pt-3 text-xs text-muted-foreground">
              <span>Быстрый выбор:</span>
              {['A', 'B'].map((g) => (
                <button key={g} type="button" className="underline" onClick={() => selectByGrade(g)}>
                  все {g}-grade
                </button>
              ))}
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[36px]">
                  {status === 'new' && (
                    <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Выбрать все" />
                  )}
                </TableHead>
                <TableHead className="w-[28px]" />
                <TableHead>Позиция</TableHead>
                <TableHead>Роль</TableHead>
                <TableHead className="text-right">Тек. цена</TableHead>
                <TableHead className="text-right">Реком.</TableHead>
                <TableHead className="text-right">Δ%</TableHead>
                <TableHead className="text-right">Ожид. ΔGP</TableHead>
                <TableHead className="text-center">ε</TableHead>
                <TableHead className="text-center">Статус</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => (
                <RecRow
                  key={r.id}
                  rec={r}
                  expanded={expanded === r.id}
                  onToggleExpand={() => setExpanded((p) => (p === r.id ? null : r.id))}
                  selectable={status === 'new' && r.status === 'new'}
                  checked={selected.has(r.id)}
                  onToggleCheck={() => toggleOne(r.id)}
                  onApprove={() => approveOne(r.id)}
                  onReject={() => { setRejectTarget(r.id); setRejectComment('') }}
                  busy={reviewMut.isPending}
                />
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Показано {filtered.length} из {total.toLocaleString('ru-RU')} · стр. {page + 1}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => { setPage((p) => Math.max(0, p - 1)); resetSelection() }} disabled={page === 0}>←</Button>
              <Button variant="outline" size="sm" onClick={() => { setPage((p) => p + 1); resetSelection() }} disabled={items.length < PAGE_SIZE}>→</Button>
            </div>
          </div>
        </Card>
      )}

      {/* Reject single dialog */}
      <Dialog open={rejectTarget != null} onOpenChange={(o) => { if (!o) { setRejectTarget(null); setRejectComment('') } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Отклонить рекомендацию</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label className="text-xs">Комментарий (необязательно)</Label>
            <Textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              placeholder="Причина отклонения…"
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRejectTarget(null); setRejectComment('') }}>Отмена</Button>
            <Button variant="destructive" onClick={confirmReject} disabled={reviewMut.isPending}>Отклонить</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Batch confirm */}
      <ConfirmDialog
        open={batchConfirm != null}
        onOpenChange={(o) => { if (!o) setBatchConfirm(null) }}
        title={batchConfirm === 'approve' ? 'Утвердить выбранные?' : 'Отклонить выбранные?'}
        description={`Действие будет применено к ${selected.size} рекомендациям.`}
        confirmText={batchConfirm === 'approve' ? 'Утвердить' : 'Отклонить'}
        destructive={batchConfirm === 'reject'}
        onConfirm={runBatch}
      />

      {/* Generate confirm */}
      <ConfirmDialog
        open={generateConfirm}
        onOpenChange={setGenerateConfirm}
        title="Сгенерировать рекомендации?"
        description="Оптимизатор пересчитает рекомендации для выбранного подразделения. Старые «новые» рекомендации старше 14 дней будут помечены как истёкшие."
        confirmText="Сгенерировать"
        onConfirm={runGenerate}
      />
    </div>
  )
}

interface RecRowProps {
  rec: PriceRecommendation
  expanded: boolean
  onToggleExpand: () => void
  selectable: boolean
  checked: boolean
  onToggleCheck: () => void
  onApprove: () => void
  onReject: () => void
  busy: boolean
}

function RecRow({
  rec, expanded, onToggleExpand, selectable, checked, onToggleCheck, onApprove, onReject, busy,
}: RecRowProps) {
  const up = (rec.delta_pct ?? 0) >= 0
  const gpUp = (rec.delta_gp ?? 0) >= 0
  return (
    <>
      <TableRow className="hover:bg-muted/40">
        <TableCell>
          {selectable && (
            <input type="checkbox" checked={checked} onChange={onToggleCheck} aria-label="Выбрать" />
          )}
        </TableCell>
        <TableCell>
          <button type="button" onClick={onToggleExpand} className="text-muted-foreground">
            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        </TableCell>
        <TableCell>
          <Link
            to={`/pricing/position/${rec.product_id}/${rec.department_id}`}
            className="text-sm font-medium hover:underline"
            style={{ color: 'var(--accent)' }}
          >
            {rec.product_name ?? `#${rec.product_id}`}
          </Link>
          {rec.department_name && (
            <div className="text-xs text-muted-foreground">{rec.department_name}</div>
          )}
        </TableCell>
        <TableCell>
          <Badge variant="outline">{menuRoleLabel(rec.menu_role)}</Badge>
        </TableCell>
        <TableCell className="text-right tabular">{formatCurrency(rec.current_price)}</TableCell>
        <TableCell className="text-right tabular font-medium">{formatCurrency(rec.recommended_price)}</TableCell>
        <TableCell className="text-right tabular">
          <span className="inline-flex items-center gap-0.5" style={{ color: up ? 'var(--pos)' : 'var(--neg)' }}>
            {up ? <ArrowUp size={11} /> : <ArrowDown size={11} />}{fmtPctSigned(rec.delta_pct)}
          </span>
        </TableCell>
        <TableCell className="text-right tabular" style={{ color: gpUp ? 'var(--pos)' : 'var(--neg)' }}>
          {rec.delta_gp != null ? formatCurrency(rec.delta_gp) : '—'}
        </TableCell>
        <TableCell className="text-center">
          <span style={{ color: gradeColor(rec.elasticity_grade), fontWeight: 600 }} title={`ε = ${rec.elasticity_used ?? '—'}`}>
            {rec.elasticity_grade ?? '—'}
          </span>
        </TableCell>
        <TableCell className="text-center">
          <Badge variant={statusBadgeVariant(rec.status)}>{statusLabel(rec.status)}</Badge>
        </TableCell>
        <TableCell className="text-right">
          {rec.status === 'new' ? (
            <div className="flex justify-end gap-1">
              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={onApprove} disabled={busy} title="Утвердить">
                <Check size={15} style={{ color: 'var(--pos)' }} />
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={onReject} disabled={busy} title="Отклонить">
                <X size={15} style={{ color: 'var(--neg)' }} />
              </Button>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={11} className="bg-muted/30">
            <div className="grid gap-4 p-2 md:grid-cols-2">
              <div>
                <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Обоснование (ИИ)</div>
                <LlmExplanation rec={rec} />
                {rec.review_comment && (
                  <p className="text-xs mt-2"><span className="text-muted-foreground">Комментарий ревью:</span> {rec.review_comment}</p>
                )}
              </div>
              <div className="text-sm space-y-1">
                <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Расчёт</div>
                <Detail label="Себестоимость (COGS)" value={rec.cogs != null ? formatCurrency(rec.cogs) : '—'} />
                <Detail
                  label="Прогноз спроса"
                  value={`${rec.current_qty_forecast ?? '—'} → ${rec.new_qty_forecast ?? '—'} шт/нед`}
                />
                <Detail label="GP" value={`${rec.current_gp != null ? formatCurrency(rec.current_gp) : '—'} → ${rec.expected_gp != null ? formatCurrency(rec.expected_gp) : '—'}`} />
                <Detail label="Эластичность" value={`${rec.elasticity_used ?? '—'} (grade ${rec.elasticity_grade ?? '—'})`} />
                {rec.constraints_applied && rec.constraints_applied.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {rec.constraints_applied.map((c) => (
                      <Badge key={c} variant="secondary" className="text-[10px]">{c}</Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular">{value}</span>
    </div>
  )
}
