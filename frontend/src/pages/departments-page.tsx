import { useState, useMemo } from 'react'
import {
  useDepartments,
  useCreateDepartment,
  useUpdateDepartment,
  useDeleteDepartment,
  useSyncDepartments,
} from '@/hooks/use-departments'
import type { Department, DepartmentCreate, DepartmentUpdate, SegmentType } from '@/types/department'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { ErrorAlert } from '@/components/shared/error-alert'
import { EmptyState } from '@/components/shared/empty-state'
import { SEGMENT_LABELS, TYPE_LABELS, formatDate } from '@/lib/formatters'
import { RefreshCw, Plus, Pencil, Trash2, Search } from 'lucide-react'

const SEGMENT_OPTIONS: { value: SegmentType; label: string }[] = [
  { value: 'restaurant', label: 'Ресторан' },
  { value: 'coffeehouse', label: 'Кофейня' },
  { value: 'confectionery', label: 'Кондитерская' },
  { value: 'food_court', label: 'Фуд-корт' },
  { value: 'store', label: 'Магазин' },
  { value: 'fast_food', label: 'Фаст-фуд' },
  { value: 'bakery', label: 'Пекарня' },
  { value: 'cafe', label: 'Кафе' },
  { value: 'bar', label: 'Бар' },
]

export function DepartmentsPage() {
  const { data: departments = [], isLoading, error, refetch } = useDepartments(true)
  const createMutation = useCreateDepartment()
  const updateMutation = useUpdateDepartment()
  const deleteMutation = useDeleteDepartment()
  const syncMutation = useSyncDepartments()

  const [typeFilter, setTypeFilter] = useState('ALL')
  const [companyFilter, setCompanyFilter] = useState('__all__')
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<Department | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)

  // Form state
  const [formData, setFormData] = useState<DepartmentCreate>({
    name: '',
    code: '',
    code_tco: '',
    type: 'DEPARTMENT',
    taxpayer_id_number: '',
    segment_type: 'restaurant',
    season_start_date: null,
    season_end_date: null,
  })

  // Company list for filter
  const companies = useMemo(() => {
    const parents = departments.filter((d) => d.type === 'JURPERSON' || d.type === 'CORPORATION')
    return parents.sort((a, b) => a.name.localeCompare(b.name))
  }, [departments])

  // Filtered departments
  const filtered = useMemo(() => {
    let result = departments
    if (typeFilter !== 'ALL') {
      result = result.filter((d) => d.type === typeFilter)
    }
    if (companyFilter !== '__all__') {
      result = result.filter((d) => d.parent_id === companyFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          (d.code && d.code.toLowerCase().includes(q)) ||
          d.id.toLowerCase().includes(q),
      )
    }
    return result
  }, [departments, typeFilter, companyFilter, search])

  const openCreateForm = () => {
    setEditingDept(null)
    setFormData({
      name: '',
      code: '',
      code_tco: '',
      type: 'DEPARTMENT',
      taxpayer_id_number: '',
      segment_type: 'restaurant',
      season_start_date: null,
      season_end_date: null,
    })
    setFormOpen(true)
  }

  const openEditForm = (dept: Department) => {
    setEditingDept(dept)
    setFormData({
      name: dept.name,
      code: dept.code || '',
      code_tco: dept.code_tco || '',
      type: dept.type,
      taxpayer_id_number: dept.taxpayer_id_number || '',
      segment_type: dept.segment_type || 'restaurant',
      season_start_date: dept.season_start_date,
      season_end_date: dept.season_end_date,
    })
    setFormOpen(true)
  }

  const handleSubmit = async () => {
    const payload: DepartmentCreate | DepartmentUpdate = { ...formData }
    if (!payload.season_start_date) {
      payload.season_start_date = null
    }
    if (!payload.season_end_date) {
      payload.season_end_date = null
    }

    if (editingDept) {
      await updateMutation.mutateAsync({ id: editingDept.id, data: payload })
    } else {
      await createMutation.mutateAsync(payload as DepartmentCreate)
    }
    setFormOpen(false)
  }

  const handleDelete = async () => {
    if (deleteTarget) {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
    }
  }

  const handleSync = () => {
    syncMutation.mutate()
  }

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Подразделения</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSync} disabled={syncMutation.isPending}>
            <RefreshCw className={`h-4 w-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            Синхронизация
          </Button>
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Обновить
          </Button>
          <Button onClick={openCreateForm}>
            <Plus className="h-4 w-4 mr-2" />
            Добавить
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Тип</Label>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">Все типы</SelectItem>
                  <SelectItem value="DEPARTMENT">Подразделения</SelectItem>
                  <SelectItem value="JURPERSON">Юр. лица</SelectItem>
                  <SelectItem value="CORPORATION">Корпорации</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Компания</Label>
              <Select value={companyFilter} onValueChange={setCompanyFilter}>
                <SelectTrigger className="w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">Все компании</SelectItem>
                  {companies.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 flex-1 min-w-[200px]">
              <Label className="text-xs">Поиск</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Поиск по имени, коду, ID..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <div className="text-sm text-muted-foreground">
              Найдено: <span className="font-semibold">{filtered.length}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      {isLoading ? (
        <LoadingSpinner />
      ) : filtered.length === 0 ? (
        <EmptyState />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Код</TableHead>
                <TableHead>Название</TableHead>
                <TableHead>Тип</TableHead>
                <TableHead>Сегмент</TableHead>
                <TableHead>ИНН</TableHead>
                <TableHead>Сезон</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((dept) => (
                <TableRow key={dept.id}>
                  <TableCell className="font-mono text-xs">{dept.code || '—'}</TableCell>
                  <TableCell className="font-medium">{dept.name}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{TYPE_LABELS[dept.type] || dept.type}</Badge>
                  </TableCell>
                  <TableCell>{dept.segment_type ? SEGMENT_LABELS[dept.segment_type] || dept.segment_type : '—'}</TableCell>
                  <TableCell className="text-xs">{dept.taxpayer_id_number || '—'}</TableCell>
                  <TableCell className="text-xs">
                    {dept.season_start_date
                      ? `${formatDate(dept.season_start_date)} — ${formatDate(dept.season_end_date)}`
                      : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEditForm(dept)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(dept)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingDept ? 'Редактировать подразделение' : 'Новое подразделение'}
            </DialogTitle>
            <DialogDescription>
              {editingDept ? 'Измените данные подразделения' : 'Заполните данные нового подразделения'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {editingDept && (
              <div className="space-y-1">
                <Label>ID</Label>
                <Input value={editingDept.id} disabled />
              </div>
            )}
            <div className="space-y-1">
              <Label>Название *</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Код</Label>
                <Input
                  value={formData.code || ''}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label>Код ТСО</Label>
                <Input
                  value={formData.code_tco || ''}
                  onChange={(e) => setFormData({ ...formData, code_tco: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Тип</Label>
                <Select
                  value={formData.type || 'DEPARTMENT'}
                  onValueChange={(v) => setFormData({ ...formData, type: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="DEPARTMENT">Подразделение</SelectItem>
                    <SelectItem value="JURPERSON">Юр. лицо</SelectItem>
                    <SelectItem value="CORPORATION">Корпорация</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Сегмент</Label>
                <Select
                  value={formData.segment_type || 'restaurant'}
                  onValueChange={(v) => setFormData({ ...formData, segment_type: v as SegmentType })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SEGMENT_OPTIONS.map((s) => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>ИНН</Label>
              <Input
                value={formData.taxpayer_id_number || ''}
                onChange={(e) => setFormData({ ...formData, taxpayer_id_number: e.target.value })}
              />
            </div>

            {/* Season fields - only for coffeehouse */}
            {formData.segment_type === 'coffeehouse' && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Начало сезона</Label>
                  <Input
                    type="date"
                    value={formData.season_start_date || ''}
                    onChange={(e) =>
                      setFormData({ ...formData, season_start_date: e.target.value || null })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label>Конец сезона</Label>
                  <Input
                    type="date"
                    value={formData.season_end_date || ''}
                    onChange={(e) =>
                      setFormData({ ...formData, season_end_date: e.target.value || null })
                    }
                  />
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setFormOpen(false)}>
                Отмена
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={!formData.name || createMutation.isPending || updateMutation.isPending}
              >
                {editingDept ? 'Сохранить' : 'Создать'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Удалить подразделение"
        description={`Вы уверены, что хотите удалить "${deleteTarget?.name}"? Это действие нельзя отменить.`}
        onConfirm={handleDelete}
        confirmText="Удалить"
        destructive
      />
    </div>
  )
}
