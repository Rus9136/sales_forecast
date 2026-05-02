import { useState } from 'react'
import { Plus, Copy } from 'lucide-react'
import { useBonusSchemes, useBonusPositions, useCalculationModels } from '@/hooks/use-bonus'
import { useDepartments } from '@/hooks/use-departments'
import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DepartmentSelect } from '@/components/shared/department-select'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SchemeConfigView } from '@/components/bonus/scheme-config-view'
import { SchemeEditorDialog } from '@/components/bonus/scheme-editor-dialog'
import type { BonusScheme, CalculationModel } from '@/types/bonus'

export function BonusSchemesPage() {
  const [departmentId, setDepartmentId] = useState<string>('__all__')
  const [openSchemeId, setOpenSchemeId] = useState<number | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorBase, setEditorBase] = useState<BonusScheme | null>(null)

  const filterDept = departmentId === '__all__' ? undefined : departmentId
  const { data: schemes = [], isLoading, error } = useBonusSchemes({ department_id: filterDept })
  const { data: positions = [] } = useBonusPositions()
  const { data: departments = [] } = useDepartments(true)
  const { data: models = [] } = useCalculationModels()

  const positionMap = Object.fromEntries(positions.map((p) => [p.id, p]))
  const departmentMap = Object.fromEntries(departments.map((d) => [d.id, d]))
  const modelMap = Object.fromEntries(models.map((m) => [m.code, m]))

  const openScheme = openSchemeId != null
    ? schemes.find((s) => s.id === openSchemeId)
    : undefined

  const openEditor = (base: BonusScheme | null) => {
    setEditorBase(base)
    setEditorOpen(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Схемы расчёта бонусов</h1>
        <Button onClick={() => openEditor(null)}>
          <Plus className="h-4 w-4 mr-1" /> Создать схему
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Фильтры</CardTitle>
        </CardHeader>
        <CardContent>
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} />
        </CardContent>
      </Card>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorAlert message={(error as Error).message} />}

      {!isLoading && !error && schemes.length === 0 && (
        <EmptyState text="Схемы не найдены" />
      )}

      {schemes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Схемы ({schemes.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Локация</TableHead>
                  <TableHead>Должность / Команда</TableHead>
                  <TableHead>Модель</TableHead>
                  <TableHead>Версия</TableHead>
                  <TableHead>Действует с</TableHead>
                  <TableHead>Действует по</TableHead>
                  <TableHead>Конфиг</TableHead>
                  <TableHead>Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schemes.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{departmentMap[s.department_id]?.name ?? s.department_id.slice(0, 8) + '…'}</TableCell>
                    <TableCell>
                      {s.position_id != null
                        ? positionMap[s.position_id]?.name ?? `position #${s.position_id}`
                        : <Badge variant="secondary">team #{s.team_id}</Badge>}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" title={modelMap[s.calculation_model]?.description ?? s.calculation_model}>
                        {modelMap[s.calculation_model]?.name ?? s.calculation_model}
                      </Badge>
                    </TableCell>
                    <TableCell>v{s.version}</TableCell>
                    <TableCell>{s.effective_from ?? '—'}</TableCell>
                    <TableCell>{s.effective_to ?? <Badge>активна</Badge>}</TableCell>
                    <TableCell>
                      <button
                        className="text-blue-600 hover:underline text-sm"
                        onClick={() => setOpenSchemeId(s.id)}
                      >
                        Показать
                      </button>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditor(s)}
                        title="Создать новую версию на основе этой"
                      >
                        <Copy className="h-3 w-3 mr-1" /> Новая версия
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={openSchemeId != null} onOpenChange={(o) => !o && setOpenSchemeId(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              Схема #{openSchemeId}
              {openScheme && (
                <span className="text-sm font-normal text-muted-foreground ml-2">
                  · {departmentMap[openScheme.department_id]?.name ?? '—'}
                  {openScheme.position_id != null && positionMap[openScheme.position_id]
                    ? ` · ${positionMap[openScheme.position_id].name}`
                    : openScheme.team_id != null
                    ? ` · команда #${openScheme.team_id}`
                    : ''}
                  {' · v' + openScheme.version}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          {openScheme && (
            <Tabs defaultValue="readable">
              <TabsList>
                <TabsTrigger value="readable">Параметры</TabsTrigger>
                <TabsTrigger value="json">JSON</TabsTrigger>
              </TabsList>
              <TabsContent value="readable" className="mt-4">
                <SchemeConfigView
                  model={openScheme.calculation_model as CalculationModel}
                  config={openScheme.config as Parameters<typeof SchemeConfigView>[0]['config']}
                />
              </TabsContent>
              <TabsContent value="json" className="mt-4">
                <pre className="text-xs bg-muted p-4 rounded overflow-x-auto">
                  {JSON.stringify(openScheme.config ?? {}, null, 2)}
                </pre>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      <SchemeEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        baseScheme={editorBase}
      />
    </div>
  )
}
