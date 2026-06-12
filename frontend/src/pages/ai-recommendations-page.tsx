import { useEffect, useMemo, useState } from 'react'
import { useDepartments } from '@/hooks/use-departments'
import {
  useAIAnalysisPrompts,
  useAIHistory,
  useAIPrompts,
  useAIProviders,
  useRerunAgent,
  useRunAIAnalysis,
  useUpdateAIPrompts,
} from '@/hooks/use-ai-recommendations'
import type { AIProvider } from '@/types/ai'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { daysAgo } from '@/lib/formatters'
import { Sparkles, History, Settings2, RefreshCw, AlertCircle } from 'lucide-react'

const AGENT_TITLES: Record<string, { title: string; emoji: string }> = {
  SalesAnalysisAgent: { title: 'Аналитик продаж', emoji: '📈' },
  OptimizationAgent: { title: 'Оптимизация', emoji: '🎯' },
  NarrativeAgent: { title: 'Итоговый отчёт', emoji: '📊' },
  PayrollAnalysisAgent: { title: 'ФОТ', emoji: '💰' },
  StaffingAgent: { title: 'Смены', emoji: '👥' },
  ReputationAgent: { title: 'Репутация', emoji: '⭐' },
}

export function AIRecommendationsPage() {
  const [departmentId, setDepartmentId] = useState<string>('')
  const [fromDate, setFromDate] = useState(daysAgo(7))
  const [toDate, setToDate] = useState(daysAgo(1))
  const [provider, setProvider] = useState<AIProvider>('claude')
  const [activeAnalysisId, setActiveAnalysisId] = useState<number | null>(null)
  const [promptDialogOpen, setPromptDialogOpen] = useState(false)

  const { data: departments = [] } = useDepartments(true)
  const { data: providers } = useAIProviders()
  const { data: history = [] } = useAIHistory()
  const { data: analysisDetail, isLoading: detailLoading } =
    useAIAnalysisPrompts(activeAnalysisId)

  const runAnalysis = useRunAIAnalysis()
  const rerunAgent = useRerunAgent()

  const filteredDepartments = useMemo(
    () =>
      [...departments]
        .filter((d) => d.type === 'DEPARTMENT' && d.is_active)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [departments],
  )

  // Default to most recent analysis if none selected
  useEffect(() => {
    if (activeAnalysisId == null && history.length > 0) {
      setActiveAnalysisId(history[0].id)
    }
  }, [history, activeAnalysisId])

  const onAnalyze = async () => {
    if (!departmentId) return
    try {
      const res = await runAnalysis.mutateAsync({
        department_id: departmentId,
        date_start: fromDate,
        date_end: toDate,
        provider,
      })
      setActiveAnalysisId(res.analysis_id)
    } catch (err) {
      console.error(err)
    }
  }

  const onRerun = async (agentName: string, newPrompt?: string) => {
    if (activeAnalysisId == null) return
    await rerunAgent.mutateAsync({
      analysis_id: activeAnalysisId,
      agent_name: agentName,
      new_prompt: newPrompt,
      provider,
    })
  }

  const providerOptions: AIProvider[] = providers?.supported_providers ?? [
    'claude',
    'openai',
    'gemini',
  ]

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            Рекомендации ИИ
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Мультиагентный анализ работы подразделения на основе локальных данных продаж и прогноза
          </p>
        </div>
        <Button variant="outline" onClick={() => setPromptDialogOpen(true)}>
          <Settings2 className="h-4 w-4 mr-2" />
          Промпты агентов
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Запуск анализа</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1">
              <Label className="text-xs">Подразделение</Label>
              <Select value={departmentId} onValueChange={setDepartmentId}>
                <SelectTrigger className="w-72">
                  <SelectValue placeholder="Выберите подразделение" />
                </SelectTrigger>
                <SelectContent>
                  {filteredDepartments.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DateRangePicker
              fromDate={fromDate}
              toDate={toDate}
              onFromDateChange={setFromDate}
              onToDateChange={setToDate}
            />
            <div className="space-y-1">
              <Label className="text-xs">Провайдер</Label>
              <Select
                value={provider}
                onValueChange={(v) => setProvider(v as AIProvider)}
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providerOptions.map((p) => {
                    const info = providers?.providers[p]
                    return (
                      <SelectItem key={p} value={p} disabled={!info?.configured}>
                        {p} {info?.configured ? '' : '(не настроен)'}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={onAnalyze}
              disabled={!departmentId || runAnalysis.isPending}
              className="ml-auto"
            >
              {runAnalysis.isPending ? (
                <>
                  <LoadingSpinner /> Анализ...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Запустить анализ
                </>
              )}
            </Button>
          </div>
          {runAnalysis.isPending && (
            <div className="text-sm text-muted-foreground bg-muted/50 rounded-md p-3 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                Идёт мультиагентный анализ. Это может занять 1-2 минуты —
                запускаются 3 агента последовательно (Sales → Optimization → Narrative).
              </div>
            </div>
          )}
          {runAnalysis.isError && (
            <ErrorAlert
              message={
                runAnalysis.error instanceof Error
                  ? runAnalysis.error.message
                  : 'Не удалось запустить анализ'
              }
            />
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        <div>
          {activeAnalysisId == null ? (
            <EmptyState text="Запустите новый анализ или выберите запись из истории справа" />
          ) : detailLoading ? (
            <LoadingSpinner />
          ) : !analysisDetail ? (
            <ErrorAlert message="Не удалось загрузить данные анализа" />
          ) : (
            <AnalysisView
              detail={analysisDetail}
              onRerun={onRerun}
              isRerunning={rerunAgent.isPending}
            />
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <History className="h-4 w-4" /> История анализов
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[600px] overflow-y-auto">
            {history.length === 0 && (
              <p className="text-sm text-muted-foreground">Пока нет записей</p>
            )}
            {history.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveAnalysisId(item.id)}
                className={
                  'w-full text-left p-3 rounded-md border transition-colors ' +
                  (activeAnalysisId === item.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:bg-muted/50')
                }
              >
                <div className="text-sm font-medium truncate">
                  {item.department_name || item.department_id}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {item.date_start} → {item.date_end}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="secondary" className="text-xs">
                    {item.provider}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {item.agent_count} агентов
                  </Badge>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      <PromptsEditorDialog
        open={promptDialogOpen}
        onOpenChange={setPromptDialogOpen}
      />
    </div>
  )
}

interface AnalysisViewProps {
  detail: NonNullable<ReturnType<typeof useAIAnalysisPrompts>['data']>
  onRerun: (agent: string, newPrompt?: string) => Promise<void>
  isRerunning: boolean
}

function AnalysisView({ detail, onRerun, isRerunning }: AnalysisViewProps) {
  const enabledAgents = detail.agents.filter((a) => a.enabled || a.has_result)
  const [activeAgent, setActiveAgent] = useState<string>(
    enabledAgents[0]?.agent_name || '',
  )

  useEffect(() => {
    if (enabledAgents.length && !enabledAgents.find((a) => a.agent_name === activeAgent)) {
      setActiveAgent(enabledAgents[0].agent_name)
    }
  }, [detail.analysis.id, enabledAgents, activeAgent])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {detail.analysis.department_name || 'Подразделение'}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {detail.analysis.date_start} → {detail.analysis.date_end} ·{' '}
          <Badge variant="secondary">{detail.analysis.provider}</Badge>
        </p>
      </CardHeader>
      <CardContent>
        {enabledAgents.length === 0 ? (
          <EmptyState text="Анализ не содержит результатов агентов" />
        ) : (
          <Tabs value={activeAgent} onValueChange={setActiveAgent}>
            <TabsList className="flex flex-wrap h-auto">
              {enabledAgents.map((a) => {
                const meta = AGENT_TITLES[a.agent_name] || { title: a.title, emoji: '🤖' }
                return (
                  <TabsTrigger key={a.agent_name} value={a.agent_name}>
                    <span className="mr-1">{meta.emoji}</span>
                    {meta.title}
                  </TabsTrigger>
                )
              })}
            </TabsList>
            {enabledAgents.map((a) => (
              <TabsContent key={a.agent_name} value={a.agent_name} className="mt-4">
                <AgentTab
                  agentName={a.agent_name}
                  title={AGENT_TITLES[a.agent_name]?.title || a.title}
                  result={a.result}
                  prompt={a.prompt}
                  onRerun={onRerun}
                  isRerunning={isRerunning}
                />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </CardContent>
    </Card>
  )
}

interface AgentTabProps {
  agentName: string
  title: string
  result: string | null
  prompt: import('@/types/ai').AIPromptLog | null
  onRerun: (agent: string, newPrompt?: string) => Promise<void>
  isRerunning: boolean
}

function AgentTab({ agentName, result, prompt, onRerun, isRerunning }: AgentTabProps) {
  const [subTab, setSubTab] = useState<'result' | 'prompt'>('result')

  return (
    <div className="space-y-4">
      <Tabs value={subTab} onValueChange={(v) => setSubTab(v as 'result' | 'prompt')}>
        <TabsList>
          <TabsTrigger value="result">Результат</TabsTrigger>
          <TabsTrigger value="prompt" disabled={!prompt}>
            Промпт
          </TabsTrigger>
        </TabsList>
        <TabsContent value="result" className="mt-4 space-y-3">
          {result ? (
            <div className="prose prose-sm max-w-none whitespace-pre-wrap bg-muted/30 rounded-md p-4 text-sm">
              {result}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Результат отсутствует</p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRerun(agentName)}
            disabled={isRerunning}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-2" />
            Перезапустить агента
          </Button>
        </TabsContent>
        <TabsContent value="prompt" className="mt-4 space-y-3">
          {prompt && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div>
                  <div className="text-muted-foreground">Провайдер</div>
                  <div className="font-medium">{prompt.provider}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Токены</div>
                  <div className="font-medium">{prompt.tokens_used}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Время</div>
                  <div className="font-medium">
                    {prompt.response_time_seconds != null
                      ? `${prompt.response_time_seconds.toFixed(1)}с`
                      : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground">Статус</div>
                  <div className="font-medium">
                    {prompt.success ? '✓' : '✗'}
                  </div>
                </div>
              </div>
              {prompt.system_prompt && (
                <div>
                  <div className="text-xs font-medium text-muted-foreground mb-1">
                    System prompt
                  </div>
                  <div className="bg-muted/30 rounded-md p-3 text-xs whitespace-pre-wrap font-mono">
                    {prompt.system_prompt}
                  </div>
                </div>
              )}
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  User prompt
                </div>
                <div className="bg-muted/30 rounded-md p-3 text-xs whitespace-pre-wrap font-mono max-h-[400px] overflow-y-auto">
                  {prompt.full_prompt}
                </div>
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

interface PromptsEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function PromptsEditorDialog({ open, onOpenChange }: PromptsEditorDialogProps) {
  const { data: prompts = [] } = useAIPrompts()
  const updateMutation = useUpdateAIPrompts()
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    if (open && prompts.length) {
      setDrafts(Object.fromEntries(prompts.map((p) => [p.agent_name, p.prompt])))
    }
  }, [open, prompts])

  const dirty = useMemo(
    () => prompts.filter((p) => drafts[p.agent_name] != null && drafts[p.agent_name] !== p.prompt),
    [prompts, drafts],
  )

  const onSave = async () => {
    if (!dirty.length) return
    await updateMutation.mutateAsync(
      Object.fromEntries(dirty.map((p) => [p.agent_name, drafts[p.agent_name]])),
    )
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Промпты агентов</DialogTitle>
          <DialogDescription>
            Шаблоны хранятся в БД. Плейсхолдеры: {`{forecast}, {plan_vs_fact}, {hourly_sales}, {department_info}, {agent_results}`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {prompts.map((p) => (
            <div key={p.agent_name} className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">
                  {AGENT_TITLES[p.agent_name]?.emoji || '🤖'} {p.agent_name}
                </Label>
                <Badge variant="outline" className="text-xs">
                  {p.source === 'db' ? 'из БД' : 'дефолт'}
                </Badge>
              </div>
              <Textarea
                rows={6}
                value={drafts[p.agent_name] ?? p.prompt}
                onChange={(e) =>
                  setDrafts((prev) => ({ ...prev, [p.agent_name]: e.target.value }))
                }
                className="font-mono text-xs"
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            onClick={onSave}
            disabled={!dirty.length || updateMutation.isPending}
          >
            {updateMutation.isPending
              ? 'Сохранение...'
              : `Сохранить (${dirty.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
