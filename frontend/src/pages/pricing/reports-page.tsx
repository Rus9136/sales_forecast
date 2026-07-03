import { useState } from 'react'
import { FileText, Sparkles, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
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
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorAlert } from '@/components/shared/error-alert'
import {
  usePricingReports, usePricingReport, useGeneratePricingReport,
} from '@/hooks/use-pricing'
import { usePricingScope } from '@/contexts/pricing-context'
import { formatCurrency, formatDate, formatDateTime } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type { ReportType, PricingReportListItem } from '@/types/pricing'

const ALL = '__all__'

const TYPE_LABEL: Record<string, string> = { weekly: 'Недельный', monthly: 'Месячный' }

function statusBadge(s: string): { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string } {
  if (s === 'ok') return { variant: 'default', label: 'Готов' }
  if (s === 'no_llm') return { variant: 'outline', label: 'Без ИИ' }
  if (s === 'error') return { variant: 'destructive', label: 'Ошибка' }
  return { variant: 'secondary', label: s }
}

function fmtPctSigned(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

function fmtRatioPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return (v * 100).toFixed(0) + '%'
}

export function PricingReportsPage() {
  const { effectiveDepartmentId } = usePricingScope()
  const [typeFilter, setTypeFilter] = useState(ALL)
  const [openId, setOpenId] = useState<number | null>(null)
  const [genOpen, setGenOpen] = useState(false)
  const [genType, setGenType] = useState<ReportType>('weekly')
  const [genDept, setGenDept] = useState(ALL)
  const [genResult, setGenResult] = useState<string | null>(null)

  const reports = usePricingReports({
    report_type: typeFilter === ALL ? undefined : typeFilter,
    department_id: effectiveDepartmentId,
  })
  const generate = useGeneratePricingReport()

  const items = reports.data?.items ?? []

  const runGenerate = () => {
    setGenResult(null)
    generate.mutate(
      { reportType: genType, departmentId: genDept === ALL ? undefined : genDept },
      {
        onSuccess: (res) => {
          setGenResult(`Отчёт #${res.id} за ${res.period_start}…${res.period_end} — ${res.has_narrative ? 'готов' : 'без нарратива'}`)
          setGenOpen(false)
          setOpenId(res.id)
        },
      },
    )
  }

  if (reports.error) return <ErrorAlert message={(reports.error as Error).message} />

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div className="seg">
          {[{ k: ALL, l: 'Все' }, { k: 'weekly', l: 'Недельные' }, { k: 'monthly', l: 'Месячные' }].map((t) => (
            <button key={t.k} type="button" className={cn(typeFilter === t.k && 'active')} onClick={() => setTypeFilter(t.k)}>
              {t.l}
            </button>
          ))}
        </div>
        <span className="pricing-hint">
          ИИ пишет сводку по итогам недели (пн 08:00) и месяца (1-е число): что сработало, что нет.
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button variant="outline" onClick={() => reports.refetch()}>
            <RotateCcw className="h-4 w-4 mr-2" /> Обновить
          </Button>
          <Button onClick={() => setGenOpen(true)}>
            <Sparkles className="h-4 w-4 mr-2" /> Сгенерировать
          </Button>
        </div>
      </div>

      {genResult && (
        <Card><div className="p-3 text-sm"><span className="font-medium">Готово:</span> {genResult}</div></Card>
      )}

      {reports.isLoading ? (
        <LoadingSpinner />
      ) : items.length === 0 ? (
        <EmptyState text="Отчётов пока нет. Сгенерируйте первый или дождитесь планировщика (пн 08:00 / 1-е число)." />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Тип</TableHead>
                <TableHead>Период</TableHead>
                <TableHead>Охват</TableHead>
                <TableHead className="text-right">GP</TableHead>
                <TableHead className="text-right">ΔGP</TableHead>
                <TableHead className="text-right">Hit-rate</TableHead>
                <TableHead className="text-center">Статус</TableHead>
                <TableHead className="whitespace-nowrap">Создан</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <ReportRow key={r.id} r={r} onOpen={() => setOpenId(r.id)} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <ReportDetailDialog id={openId} onClose={() => setOpenId(null)} />

      {/* Generate dialog */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Сгенерировать отчёт</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Тип отчёта</Label>
              <Select value={genType} onValueChange={(v) => setGenType(v as ReportType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="weekly">Недельный (прошлая неделя)</SelectItem>
                  <SelectItem value="monthly">Месячный (прошлый месяц)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DepartmentSelect value={genDept} onChange={setGenDept} includeInactive label="Охват (или вся сеть)" />
            <p className="text-xs text-muted-foreground">
              Генерация зовёт LLM и занимает ~30–60 секунд. Числа берутся строго из данных за период.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenOpen(false)}>Отмена</Button>
            <Button onClick={runGenerate} disabled={generate.isPending}>
              {generate.isPending ? 'Генерация…' : 'Сгенерировать'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function ReportRow({ r, onOpen }: { r: PricingReportListItem; onOpen: () => void }) {
  const k = r.kpis
  const sb = statusBadge(r.status)
  const gpUp = (k?.gp_delta_pct ?? 0) >= 0
  return (
    <TableRow className="cursor-pointer hover:bg-muted/40" onClick={onOpen}>
      <TableCell><Badge variant="outline">{TYPE_LABEL[r.report_type] ?? r.report_type}</Badge></TableCell>
      <TableCell className="text-sm whitespace-nowrap">{formatDate(r.period_start)} – {formatDate(r.period_end)}</TableCell>
      <TableCell className="text-sm">{r.scope === 'network' ? 'Вся сеть' : (r.department_name ?? 'Точка')}</TableCell>
      <TableCell className="text-right tabular">{k?.gross_profit != null ? formatCurrency(k.gross_profit) : '—'}</TableCell>
      <TableCell className="text-right tabular" style={{ color: gpUp ? 'var(--pos)' : 'var(--neg)' }}>
        {fmtPctSigned(k?.gp_delta_pct)}
      </TableCell>
      <TableCell className="text-right tabular">{fmtRatioPct(k?.hit_rate)}</TableCell>
      <TableCell className="text-center"><Badge variant={sb.variant}>{sb.label}</Badge></TableCell>
      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">{formatDateTime(r.created_at)}</TableCell>
    </TableRow>
  )
}

function ReportDetailDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const detail = usePricingReport(id)
  const r = detail.data

  return (
    <Dialog open={id != null} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {r ? `${TYPE_LABEL[r.report_type] ?? r.report_type} отчёт · ${formatDate(r.period_start)} – ${formatDate(r.period_end)}` : 'Отчёт'}
          </DialogTitle>
        </DialogHeader>
        {detail.isLoading ? (
          <LoadingSpinner />
        ) : !r ? (
          <EmptyState text="Не удалось загрузить отчёт" />
        ) : (
          <div className="space-y-4">
            {/* KPI grid */}
            {r.kpis && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                <MiniKpi label="GP" value={r.kpis.gross_profit != null ? formatCurrency(r.kpis.gross_profit) : '—'}
                  foot={fmtPctSigned(r.kpis.gp_delta_pct)} footColor={(r.kpis.gp_delta_pct ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)'} />
                <MiniKpi label="Маржа GP" value={fmtRatioPct(r.kpis.gp_margin)} />
                <MiniKpi label="Средний чек" value={r.kpis.avg_receipt_sum != null ? formatCurrency(r.kpis.avg_receipt_sum) : '—'} />
                <MiniKpi label="Hit-rate" value={fmtRatioPct(r.kpis.hit_rate)} foot={`${r.kpis.outcomes_evaluated} оценок`} />
                <MiniKpi label="Утверждено" value={String(r.kpis.recs_approved)} />
                <MiniKpi label="Применено" value={String(r.kpis.recs_applied)} />
                <MiniKpi label="Факт ΔGP" value={r.kpis.actual_delta_gp != null ? formatCurrency(r.kpis.actual_delta_gp) : '—'}
                  footColor={(r.kpis.actual_delta_gp ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)'} />
                <MiniKpi label="Охват" value={r.scope === 'network' ? 'Сеть' : (r.department_name ?? 'Точка')} />
              </div>
            )}

            {/* Narrative */}
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Сводка (ИИ)</div>
              {r.narrative ? (
                <div className="prose prose-sm max-w-none whitespace-pre-wrap rounded-md p-4 text-sm" style={{ background: 'var(--surface-2)' }}>
                  {r.narrative}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Нарратив не сгенерирован {r.status === 'no_llm' ? '(LLM-провайдер не настроен)' : ''}.
                </p>
              )}
            </div>

            <div className="text-xs text-muted-foreground">
              {r.provider}{r.model ? ` · ${r.model}` : ''} · создан {formatDateTime(r.created_at)}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function MiniKpi({ label, value, foot, footColor }: { label: string; value: string; foot?: string; footColor?: string }) {
  return (
    <div className="kpi" style={{ padding: '10px 12px' }}>
      <div className="kpi__label">{label}</div>
      <div className="kpi__value" style={{ fontSize: 18 }}>{value}</div>
      {foot && <div className="kpi__foot"><span style={{ fontSize: 11, color: footColor }}>{foot}</span></div>}
    </div>
  )
}
