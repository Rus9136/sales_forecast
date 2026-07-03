import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import {
  ChevronDown, ChevronRight, Check, X, Search, Wand2, Download, ArrowUp, ArrowDown, Sparkles,
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
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { LlmExplanation } from '@/components/shared/llm-explanation'
import { Term, GLOSSARY } from '@/components/shared/term'
import {
  useRecommendations, useRecommendationsSummary,
  useReviewRecommendation, useBatchReview, useGenerateRecommendations,
} from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { useAuth } from '@/contexts/auth-context'
import { apiDownload, apiErrorMessage } from '@/lib/api-client'
import { formatCurrency } from '@/lib/formatters'
import {
  menuRoleLabel, statusLabel, statusBadgeVariant, gradeColor, gradeWord,
  constraintLabel, MENU_ROLE_LABELS,
} from '@/lib/pricing-labels'
import type { PriceRecommendation } from '@/types/pricing'

const ALL = '__all__'
const PAGE_SIZE = 200

/** Чипы статусов = воронка цикла (те же слова, что на «Обзоре»). */
const STATUS_CHIPS: { key: string; label: string }[] = [
  { key: 'new', label: 'Новые' },
  { key: 'approved', label: 'Утверждены' },
  { key: 'applied', label: 'Применены' },
  { key: 'rejected', label: 'Отклонены' },
  { key: 'expired', label: 'Истекли' },
  { key: '', label: 'Все' },
]

type SortKey = 'delta_gp' | 'delta_pct' | 'grade'

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

function fmtCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return (value / 1_000_000).toFixed(1) + ' млн'
  if (abs >= 1_000) return (value / 1_000).toFixed(0) + ' тыс'
  return Math.round(value).toString()
}

export function PricingRecommendationsPage() {
  const { user } = useAuth()
  const reviewerId = user?.id
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()

  const { effectiveDepartmentId } = usePricingScope()

  // Статус — в URL, чтобы работали переходы с «Обзора» (?status=new)
  const status = searchParams.get('status') ?? 'new'
  const setStatus = (s: string) => {
    setSearchParams(s ? { status: s } : {}, { replace: true })
  }

  const [roleFilter, setRoleFilter] = useState(ALL)
  const [gradeFilter, setGradeFilter] = useState(ALL)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('delta_gp')
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

  // Поиск — серверный, с дебаунсом 350 мс
  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(0)
    }, 350)
    return () => clearTimeout(id)
  }, [search])

  // Сброс выделения/страницы при смене контекста
  useEffect(() => {
    setSelected(new Set())
    setPage(0)
  }, [effectiveDepartmentId, status])

  const recsQuery = useRecommendations({
    department_id: effectiveDepartmentId,
    status: status || undefined,
    search: debouncedSearch || undefined,
    menu_role: roleFilter === ALL ? undefined : roleFilter,
    elasticity_grade: gradeFilter === ALL ? undefined : gradeFilter,
    sort: sortKey,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })
  const summary = useRecommendationsSummary(effectiveDepartmentId)
  const reviewMut = useReviewRecommendation()
  const batchMut = useBatchReview()
  const generateMut = useGenerateRecommendations()

  const items = recsQuery.data?.items ?? []
  const total = recsQuery.data?.total ?? 0

  const byStatus = summary.data?.by_status ?? {}
  const potentialGp = summary.data?.total_delta_gp_new ?? null

  // «Уверенные ходы»: новые A/B с положительным эффектом на текущей странице
  const sureMoves = useMemo(
    () =>
      status === 'new'
        ? items.filter(
            (r) =>
              r.status === 'new' &&
              (r.elasticity_grade === 'A' || r.elasticity_grade === 'B') &&
              (r.delta_gp ?? 0) > 0 &&
              r.rec_type !== 'experiment',
          )
        : [],
    [items, status],
  )
  const sureMovesGp = sureMoves.reduce((acc, r) => acc + (r.delta_gp ?? 0), 0)

  const reviewableOnPage = useMemo(
    () => items.filter((r) => r.status === 'new').map((r) => r.id),
    [items],
  )
  const allSelected = reviewableOnPage.length > 0 && reviewableOnPage.every((id) => selected.has(id))

  const selectedGp = useMemo(
    () =>
      items
        .filter((r) => selected.has(r.id))
        .reduce((acc, r) => acc + (r.delta_gp ?? 0), 0),
    [items, selected],
  )

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

  const selectSureMoves = () => {
    setSelected(new Set(sureMoves.map((r) => r.id)))
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
    if (!effectiveDepartmentId) return
    generateMut.mutate(
      { departmentId: effectiveDepartmentId },
      {
        onSuccess: (res) => {
          setGenResult(`Создано ${res.recommendations_created} предложений из ${res.skus_processed} позиций`)
          setGenerateConfirm(false)
        },
      },
    )
  }

  const exportStatus = status || 'approved'
  const exportLabel = `Экспорт XLSX (${statusLabel(exportStatus).toLowerCase()})`

  const handleExport = async () => {
    setExportError(null)
    try {
      const params = new URLSearchParams({ status: exportStatus })
      if (effectiveDepartmentId) params.set('department_id', effectiveDepartmentId)
      const blob = await apiDownload(`/api/pricing-engine/recommendations/export?${params}`)
      const href = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = href
      a.download = `price_recommendations_${exportStatus}.xlsx`
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

  const fromPath = { fromPath: location.pathname + location.search }

  return (
    <>
      {/* Верхняя строка: чипы статусов + действия */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div className="pricing-chips">
          {STATUS_CHIPS.map((t) => {
            const count = t.key ? byStatus[t.key as keyof typeof byStatus] : summary.data?.total
            return (
              <button
                key={t.key}
                type="button"
                className={'pricing-chip' + (status === t.key ? ' active' : '')}
                onClick={() => onFilterChange(() => setStatus(t.key))}
              >
                {t.label}
                {count != null && <span className="c">{count.toLocaleString('ru-RU')}</span>}
              </button>
            )
          })}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button variant="outline" onClick={handleExport} title="Скачать таблицу для загрузки цен в iiko">
            <Download className="h-4 w-4 mr-2" /> {exportLabel}
          </Button>
          <Button
            onClick={() => setGenerateConfirm(true)}
            disabled={!effectiveDepartmentId || generateMut.isPending}
          >
            <Wand2 className={`h-4 w-4 mr-2 ${generateMut.isPending ? 'animate-spin' : ''}`} />
            {generateMut.isPending ? 'Пересчёт…' : 'Пересчитать предложения'}
          </Button>
        </div>
      </div>

      {/* Причина недоступности — на экране, не в тултипе */}
      {!effectiveDepartmentId && (
        <span className="pricing-hint">
          Чтобы пересчитать предложения вручную, выберите точку в шапке раздела. Ночной
          пересчёт (05:00) идёт по всем точкам автоматически.
        </span>
      )}

      {status === 'new' && potentialGp != null && potentialGp > 0 && (
        <span className="pricing-hint">
          Потенциал всех новых предложений:{' '}
          <b style={{ color: 'var(--pos)' }}>
            +{fmtCompact(potentialGp)} ₸/нед{' '}
            <Term tip={GLOSSARY.deltaGp}>прибыли</Term>
          </b>
        </span>
      )}

      {genResult && (
        <Card><CardContent className="p-3 text-sm"><span className="font-medium">Готово:</span> {genResult}</CardContent></Card>
      )}
      {exportError && <ErrorAlert message={`Экспорт не удался: ${exportError}`} />}
      {reviewMut.error && <ErrorAlert message={apiErrorMessage(reviewMut.error)} title="Действие не выполнено" />}
      {batchMut.error && <ErrorAlert message={apiErrorMessage(batchMut.error)} title="Массовое действие не выполнено" />}
      {generateMut.error && <ErrorAlert message={apiErrorMessage(generateMut.error)} title="Пересчёт не выполнен" />}

      {/* «Уверенные ходы» */}
      {sureMoves.length > 0 && (
        <div className="pricing-sure">
          <div>
            <b>
              Уверенные ходы: {sureMoves.length}{' '}
              <span style={{ color: 'var(--pos)', fontFamily: 'var(--font-mono)' }}>
                +{fmtCompact(sureMovesGp)} ₸/нед
              </span>
            </b>
            <div className="ds">
              <Term tip={GLOSSARY.grade}>Высокая и хорошая надёжность (A/B)</Term> — у этих блюд
              достаточно истории, чтобы доверять прогнозу.
            </div>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Button size="sm" onClick={() => { selectSureMoves(); setBatchConfirm('approve') }} disabled={batchMut.isPending}>
              <Sparkles className="h-4 w-4 mr-1" /> Утвердить все {sureMoves.length}
            </Button>
            <Button size="sm" variant="outline" onClick={selectSureMoves}>
              Выбрать в списке
            </Button>
          </div>
        </div>
      )}

      {/* Фильтры (серверные — по всей базе) */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Поиск по блюду</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Название…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9 w-56"
                />
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
              <Label className="text-xs">Надёжность оценки</Label>
              <Select value={gradeFilter} onValueChange={(v) => onFilterChange(() => setGradeFilter(v))}>
                <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Любая</SelectItem>
                  {(['A', 'B', 'C', 'D'] as const).map((g) => (
                    <SelectItem key={g} value={g}>{gradeWord(g)} · {g}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Сортировка</Label>
              <Select value={sortKey} onValueChange={(v) => onFilterChange(() => setSortKey(v as SortKey))}>
                <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="delta_gp">По приросту прибыли</SelectItem>
                  <SelectItem value="delta_pct">По размеру изменения</SelectItem>
                  <SelectItem value="grade">По надёжности</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Панель массовых действий */}
      {selected.size > 0 && (
        <Card>
          <CardContent className="p-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">
              Выбрано: {selected.size}
              {selectedGp > 0 && (
                <span style={{ color: 'var(--pos)', fontFamily: 'var(--font-mono)', marginLeft: 8 }}>
                  +{fmtCompact(selectedGp)} ₸/нед
                </span>
              )}
            </span>
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
      ) : items.length === 0 ? (
        <EmptyState
          text={
            status === 'new'
              ? 'Новых предложений нет. Они появляются после ночного пересчёта (05:00); можно пересчитать вручную кнопкой выше, выбрав точку.'
              : 'Ничего не найдено под выбранные фильтры.'
          }
        />
      ) : (
        <Card>
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
                <TableHead>Изменение цены</TableHead>
                <TableHead className="text-right">
                  <Term tip={GLOSSARY.deltaGp}>Прибыль/нед</Term>
                </TableHead>
                <TableHead className="text-center">
                  <Term tip={GLOSSARY.grade}>Надёжность</Term>
                </TableHead>
                <TableHead className="text-center">Статус</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <RecRow
                  key={r.id}
                  rec={r}
                  fromPath={fromPath}
                  expanded={expanded === r.id}
                  onToggleExpand={() => setExpanded((p) => (p === r.id ? null : r.id))}
                  selectable={r.status === 'new'}
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
              Всего: {total.toLocaleString('ru-RU')} · стр. {page + 1} из {Math.max(1, Math.ceil(total / PAGE_SIZE))}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => { setPage((p) => Math.max(0, p - 1)); resetSelection() }} disabled={page === 0}>←</Button>
              <Button variant="outline" size="sm" onClick={() => { setPage((p) => p + 1); resetSelection() }} disabled={(page + 1) * PAGE_SIZE >= total}>→</Button>
            </div>
          </div>
        </Card>
      )}

      {/* Reject single dialog */}
      <Dialog open={rejectTarget != null} onOpenChange={(o) => { if (!o) { setRejectTarget(null); setRejectComment('') } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Отклонить предложение</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label className="text-xs">Комментарий (необязательно)</Label>
            <Textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              placeholder="Почему отклоняете — попадёт в журнал действий…"
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
        description={
          `Действие будет применено к ${selected.size} предложениям` +
          (batchConfirm === 'approve' && selectedGp > 0
            ? ` (ожидаемый эффект +${fmtCompact(selectedGp)} ₸/нед). После утверждения скачайте XLSX и загрузите цены в iiko.`
            : '.')
        }
        confirmText={batchConfirm === 'approve' ? 'Утвердить' : 'Отклонить'}
        destructive={batchConfirm === 'reject'}
        onConfirm={runBatch}
      />

      {/* Generate confirm */}
      <ConfirmDialog
        open={generateConfirm}
        onOpenChange={setGenerateConfirm}
        title="Пересчитать предложения?"
        description="Оптимизатор заново рассчитает выгодные изменения цен для выбранной точки. Прежние непросмотренные предложения будут заменены свежими."
        confirmText="Пересчитать"
        onConfirm={runGenerate}
      />
    </>
  )
}

interface RecRowProps {
  rec: PriceRecommendation
  fromPath: { fromPath: string }
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
  rec, fromPath, expanded, onToggleExpand, selectable, checked, onToggleCheck, onApprove, onReject, busy,
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
          <button type="button" onClick={onToggleExpand} className="text-muted-foreground" title="Почему такая цена">
            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        </TableCell>
        <TableCell>
          <Link
            to={`/pricing/position/${rec.product_id}/${rec.department_id}`}
            state={fromPath}
            className="text-sm font-medium hover:underline"
            style={{ color: 'var(--accent)' }}
          >
            {rec.product_name ?? `#${rec.product_id}`}
          </Link>
          {rec.rec_type === 'experiment' && (
            <Badge
              variant="outline"
              className="ml-2 align-middle text-[10px]"
              style={{ color: 'var(--info)', borderColor: 'var(--info)' }}
            >
              <Term tip={GLOSSARY.experiment}>Эксперимент</Term>
            </Badge>
          )}
          <div className="text-xs text-muted-foreground">
            {menuRoleLabel(rec.menu_role)}
            {rec.department_name ? ` · ${rec.department_name}` : ''}
          </div>
        </TableCell>
        <TableCell className="whitespace-nowrap">
          <span className="tabular text-sm">
            <span style={{ color: 'var(--text-subtle)', textDecoration: 'line-through' }}>
              {formatCurrency(rec.current_price)}
            </span>
            <span style={{ color: 'var(--text-subtle)', margin: '0 6px' }}>→</span>
            <span style={{ fontWeight: 650 }}>{formatCurrency(rec.recommended_price)}</span>
          </span>
          <span
            className="inline-flex items-center gap-0.5 tabular text-xs ml-2"
            style={{ color: up ? 'var(--pos)' : 'var(--neg)' }}
          >
            {up ? <ArrowUp size={11} /> : <ArrowDown size={11} />}{fmtPctSigned(rec.delta_pct)}
          </span>
        </TableCell>
        <TableCell className="text-right tabular" style={{ color: gpUp ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
          {rec.rec_type === 'experiment'
            ? <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>замер спроса</span>
            : rec.delta_gp != null ? `${rec.delta_gp > 0 ? '+' : ''}${formatCurrency(rec.delta_gp)}` : '—'}
        </TableCell>
        <TableCell className="text-center">
          <span className="inline-flex items-center gap-1.5 text-xs" style={{ fontWeight: 600 }}>
            <span
              style={{
                width: 7, height: 7, borderRadius: 999,
                background: gradeColor(rec.elasticity_grade), display: 'inline-block',
              }}
            />
            {gradeWord(rec.elasticity_grade)}
            {rec.elasticity_grade && (
              <span style={{ color: 'var(--text-subtle)', fontWeight: 500 }}>· {rec.elasticity_grade}</span>
            )}
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
          <TableCell colSpan={8} className="bg-muted/30">
            <div className="p-2 space-y-3">
              <div>
                <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Почему система это предлагает
                </div>
                <LlmExplanation rec={rec} />
                {rec.review_comment && (
                  <p className="text-xs mt-2">
                    <span className="text-muted-foreground">Комментарий при решении:</span> {rec.review_comment}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span>Себестоимость <b className="tabular" style={{ color: 'var(--text)' }}>{rec.cogs != null ? formatCurrency(rec.cogs) : '—'}</b></span>
                <span>Прогноз спроса <b className="tabular" style={{ color: 'var(--text)' }}>{rec.current_qty_forecast ?? '—'} → {rec.new_qty_forecast ?? '—'} шт/нед</b></span>
                <span>Прибыль/нед <b className="tabular" style={{ color: 'var(--text)' }}>{rec.current_gp != null ? formatCurrency(rec.current_gp) : '—'} → {rec.expected_gp != null ? formatCurrency(rec.expected_gp) : '—'}</b></span>
                <span>
                  <Term tip={GLOSSARY.elasticity}>Чувствительность спроса</Term>{' '}
                  <b className="tabular" style={{ color: 'var(--text)' }}>{rec.elasticity_used ?? '—'}</b>{' '}
                  ({gradeWord(rec.elasticity_grade)})
                </span>
              </div>
              {rec.constraints_applied && rec.constraints_applied.length > 0 && (
                <div className="flex flex-wrap items-center gap-1">
                  <span className="text-xs text-muted-foreground mr-1">Пройденные ограничения:</span>
                  {rec.constraints_applied.map((c) => (
                    <Badge key={c} variant="secondary" className="text-[10px]">✓ {constraintLabel(c)}</Badge>
                  ))}
                </div>
              )}
              <div>
                <Link
                  to={`/pricing/position/${rec.product_id}/${rec.department_id}`}
                  state={fromPath}
                  className="text-xs font-medium hover:underline"
                  style={{ color: 'var(--accent)' }}
                >
                  Открыть карточку блюда: история цены, кривая спроса, прошлые решения →
                </Link>
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
