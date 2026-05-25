import { useState, useMemo } from 'react'
import {
  useDepartments,
  useCreateDepartment,
  useUpdateDepartment,
  useDeleteDepartment,
  useSyncDepartments,
} from '@/hooks/use-departments'
import type {
  Department,
  DepartmentCreate,
  DepartmentUpdate,
  SegmentType,
  LocationType,
  SeasonalityIntensity,
} from '@/types/department'
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
import {
  SEGMENT_LABELS,
  TYPE_LABELS,
  LOCATION_TYPE_LABELS,
  SEASONALITY_LABELS,
  MONTH_LABELS,
  formatDate,
} from '@/lib/formatters'
import { KNOWN_IIKO_SOURCES, iikoSourceLabel } from '@/lib/iiko-sources'
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

const LOCATION_TYPE_OPTIONS: { value: LocationType; label: string }[] = [
  { value: 'city_center', label: 'Городской центр' },
  { value: 'mall', label: 'Торговый центр' },
  { value: 'business_district', label: 'Бизнес-район' },
  { value: 'resort_mountain', label: 'Резорт (горы)' },
  { value: 'resort_lake', label: 'Резорт (озеро)' },
  { value: 'visit_center', label: 'Визит-центр' },
  { value: 'other', label: 'Другое' },
]

const SEASONALITY_OPTIONS: { value: SeasonalityIntensity; label: string }[] = [
  { value: 'none', label: 'Нет' },
  { value: 'low', label: 'Слабая' },
  { value: 'medium', label: 'Средняя' },
  { value: 'high', label: 'Сильная' },
]

const NULL_SENTINEL = '__none__'

const emptyForm = (): DepartmentCreate => ({
  name: '',
  code: '',
  code_tco: '',
  type: 'DEPARTMENT',
  taxpayer_id_number: '',
  segment_type: 'restaurant',
  season_start_date: null,
  season_end_date: null,
  brand: null,
  city: null,
  location_type: null,
  tourist_traffic_dependent: false,
  is_24_7: false,
  opening_hour: null,
  closing_hour: null,
  seasonality_intensity: 'none',
  opened_date: null,
  season_start_month: null,
  season_end_month: null,
})

export function DepartmentsPage() {
  const { data: departments = [], isLoading, error, refetch } = useDepartments(true)
  const createMutation = useCreateDepartment()
  const updateMutation = useUpdateDepartment()
  const deleteMutation = useDeleteDepartment()
  const syncMutation = useSyncDepartments()

  const [typeFilter, setTypeFilter] = useState('ALL')
  const [companyFilter, setCompanyFilter] = useState('__all__')
  const [sourceFilter, setSourceFilter] = useState('__all__')
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<Department | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)

  // Form state
  const [formData, setFormData] = useState<DepartmentCreate>(emptyForm())

  // Company list for filter
  const companies = useMemo(() => {
    const parents = departments.filter((d) => d.type === 'JURPERSON' || d.type === 'CORPORATION')
    return parents.sort((a, b) => a.name.localeCompare(b.name))
  }, [departments])

  // Datalist suggestions from existing values
  const brandSuggestions = useMemo(() => {
    const set = new Set<string>()
    for (const d of departments) {
      if (d.brand) set.add(d.brand)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [departments])

  const citySuggestions = useMemo(() => {
    const set = new Set<string>()
    for (const d of departments) {
      if (d.city) set.add(d.city)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
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
    if (sourceFilter !== '__all__') {
      result = result.filter((d) => d.iiko_source_domain === sourceFilter)
    }
    if (!showInactive) {
      result = result.filter((d) => d.is_active)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          (d.code && d.code.toLowerCase().includes(q)) ||
          (d.brand && d.brand.toLowerCase().includes(q)) ||
          (d.city && d.city.toLowerCase().includes(q)) ||
          d.id.toLowerCase().includes(q),
      )
    }
    return result
  }, [departments, typeFilter, companyFilter, sourceFilter, search, showInactive])

  // Список iiko-источников, реально присутствующих в выборке + базовые известные
  const sourceOptions = useMemo(() => {
    const present = new Set<string>()
    for (const d of departments) {
      if (d.iiko_source_domain) present.add(d.iiko_source_domain)
    }
    // Гарантируем устойчивый порядок: сначала известные (Сандык/Мадлен), затем
    // прочие, отсортированные по алфавиту
    const known = KNOWN_IIKO_SOURCES.filter((h) => present.has(h))
    const others = Array.from(present)
      .filter((h) => !KNOWN_IIKO_SOURCES.includes(h))
      .sort()
    return [...known, ...others]
  }, [departments])

  const inactiveCount = useMemo(
    () => departments.filter((d) => d.type === 'DEPARTMENT' && !d.is_active).length,
    [departments],
  )

  const openCreateForm = () => {
    setEditingDept(null)
    setFormData(emptyForm())
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
      brand: dept.brand,
      city: dept.city,
      location_type: dept.location_type,
      tourist_traffic_dependent: dept.tourist_traffic_dependent,
      is_24_7: dept.is_24_7,
      opening_hour: dept.opening_hour,
      closing_hour: dept.closing_hour,
      seasonality_intensity: dept.seasonality_intensity ?? 'none',
      opened_date: dept.opened_date,
      season_start_month: dept.season_start_month,
      season_end_month: dept.season_end_month,
    })
    setFormOpen(true)
  }

  const handleSubmit = async () => {
    const payload: DepartmentCreate | DepartmentUpdate = { ...formData }
    if (!payload.season_start_date) payload.season_start_date = null
    if (!payload.season_end_date) payload.season_end_date = null
    if (!payload.opened_date) payload.opened_date = null
    // Trim empty strings → null/undefined for optional text fields
    if (payload.brand !== undefined) payload.brand = payload.brand?.trim() || null
    if (payload.city !== undefined) payload.city = payload.city?.trim() || null
    // If 24/7 — clear opening/closing hours
    if (payload.is_24_7) {
      payload.opening_hour = null
      payload.closing_hour = null
    }
    // If no seasonality — clear season months
    if (payload.seasonality_intensity === 'none') {
      payload.season_start_month = null
      payload.season_end_month = null
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
            <div className="space-y-1">
              <Label className="text-xs">Источник iiko</Label>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">Все источники</SelectItem>
                  {sourceOptions.map((host) => (
                    <SelectItem key={host} value={host}>
                      {iikoSourceLabel(host)}
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
                  placeholder="Поиск по имени, коду, бренду, городу, ID..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Показывать неактивные
              {inactiveCount > 0 && (
                <span className="text-muted-foreground">({inactiveCount})</span>
              )}
            </label>
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
                <TableHead>Источник</TableHead>
                <TableHead>Бренд</TableHead>
                <TableHead>Локация</TableHead>
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
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="secondary">{TYPE_LABELS[dept.type] || dept.type}</Badge>
                      {dept.type === 'DEPARTMENT' && !dept.is_active && (
                        <Badge
                          variant="outline"
                          className="border-destructive/50 text-destructive"
                          title={
                            dept.last_sale_date
                              ? `Последняя продажа: ${formatDate(dept.last_sale_date)}`
                              : 'Нет продаж'
                          }
                        >
                          Неактивно
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    <span title={dept.iiko_source_domain}>
                      {iikoSourceLabel(dept.iiko_source_domain)}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{dept.brand || '—'}</TableCell>
                  <TableCell className="text-xs">
                    {dept.location_type
                      ? LOCATION_TYPE_LABELS[dept.location_type] || dept.location_type
                      : '—'}
                  </TableCell>
                  <TableCell>{dept.segment_type ? SEGMENT_LABELS[dept.segment_type] || dept.segment_type : '—'}</TableCell>
                  <TableCell className="text-xs">{dept.taxpayer_id_number || '—'}</TableCell>
                  <TableCell className="text-xs">
                    {dept.season_start_date
                      ? `${formatDate(dept.season_start_date)} — ${formatDate(dept.season_end_date)}`
                      : dept.seasonality_intensity && dept.seasonality_intensity !== 'none'
                        ? SEASONALITY_LABELS[dept.seasonality_intensity]
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
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

            {/* Season fields - only for coffeehouse (legacy seasonal date range) */}
            {formData.segment_type === 'coffeehouse' && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Начало сезона (дата)</Label>
                  <Input
                    type="date"
                    value={formData.season_start_date || ''}
                    onChange={(e) =>
                      setFormData({ ...formData, season_start_date: e.target.value || null })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label>Конец сезона (дата)</Label>
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

            {/* Operational characteristics — manual ML features */}
            <div className="border-t pt-4">
              <h3 className="text-sm font-semibold mb-3">Операционные характеристики</h3>
              <p className="text-xs text-muted-foreground mb-3">
                Используются как признаки для модели прогноза продаж. Не затираются синхронизацией iiko.
              </p>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Бренд</Label>
                  <Input
                    list="dept-brand-list"
                    placeholder="Например: Tary, Sandyq"
                    value={formData.brand || ''}
                    onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                  />
                  <datalist id="dept-brand-list">
                    {brandSuggestions.map((b) => (
                      <option key={b} value={b} />
                    ))}
                  </datalist>
                </div>
                <div className="space-y-1">
                  <Label>Город</Label>
                  <Input
                    list="dept-city-list"
                    placeholder="Например: Алматы, Боровое"
                    value={formData.city || ''}
                    onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  />
                  <datalist id="dept-city-list">
                    {citySuggestions.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="space-y-1">
                  <Label>Тип локации</Label>
                  <Select
                    value={formData.location_type ?? NULL_SENTINEL}
                    onValueChange={(v) =>
                      setFormData({
                        ...formData,
                        location_type: v === NULL_SENTINEL ? null : (v as LocationType),
                      })
                    }
                  >
                    <SelectTrigger><SelectValue placeholder="Не указано" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NULL_SENTINEL}>Не указано</SelectItem>
                      {LOCATION_TYPE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>Дата открытия</Label>
                  <Input
                    type="date"
                    value={formData.opened_date || ''}
                    onChange={(e) =>
                      setFormData({ ...formData, opened_date: e.target.value || null })
                    }
                  />
                </div>
              </div>

              <div className="flex flex-col gap-2 mt-4">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-input"
                    checked={!!formData.tourist_traffic_dependent}
                    onChange={(e) =>
                      setFormData({ ...formData, tourist_traffic_dependent: e.target.checked })
                    }
                  />
                  Зависит от туристического потока
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-input"
                    checked={!!formData.is_24_7}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        is_24_7: e.target.checked,
                        opening_hour: e.target.checked ? null : formData.opening_hour,
                        closing_hour: e.target.checked ? null : formData.closing_hour,
                      })
                    }
                  />
                  Работает 24/7
                </label>
              </div>

              {!formData.is_24_7 && (
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="space-y-1">
                    <Label>Час открытия (0–23)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={23}
                      placeholder="например, 8"
                      value={formData.opening_hour ?? ''}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          opening_hour: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>Час закрытия (0–24)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={24}
                      placeholder="например, 22"
                      value={formData.closing_hour ?? ''}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          closing_hour: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                    />
                  </div>
                </div>
              )}

              <div className="space-y-1 mt-3">
                <Label>Сезонность</Label>
                <Select
                  value={formData.seasonality_intensity ?? 'none'}
                  onValueChange={(v) =>
                    setFormData({
                      ...formData,
                      seasonality_intensity: v as SeasonalityIntensity,
                      ...(v === 'none'
                        ? { season_start_month: null, season_end_month: null }
                        : {}),
                    })
                  }
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SEASONALITY_OPTIONS.map((s) => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {formData.seasonality_intensity && formData.seasonality_intensity !== 'none' && (
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="space-y-1">
                    <Label>Месяц старта сезона</Label>
                    <Select
                      value={
                        formData.season_start_month != null
                          ? String(formData.season_start_month)
                          : NULL_SENTINEL
                      }
                      onValueChange={(v) =>
                        setFormData({
                          ...formData,
                          season_start_month: v === NULL_SENTINEL ? null : Number(v),
                        })
                      }
                    >
                      <SelectTrigger><SelectValue placeholder="Не указано" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NULL_SENTINEL}>Не указано</SelectItem>
                        {MONTH_LABELS.map((m) => (
                          <SelectItem key={m.value} value={String(m.value)}>{m.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label>Месяц конца сезона</Label>
                    <Select
                      value={
                        formData.season_end_month != null
                          ? String(formData.season_end_month)
                          : NULL_SENTINEL
                      }
                      onValueChange={(v) =>
                        setFormData({
                          ...formData,
                          season_end_month: v === NULL_SENTINEL ? null : Number(v),
                        })
                      }
                    >
                      <SelectTrigger><SelectValue placeholder="Не указано" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NULL_SENTINEL}>Не указано</SelectItem>
                        {MONTH_LABELS.map((m) => (
                          <SelectItem key={m.value} value={String(m.value)}>{m.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </div>

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
