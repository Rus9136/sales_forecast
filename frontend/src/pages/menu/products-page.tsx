import { useMemo, useState } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import {
  useNomenclatureCategories,
  useNomenclatureGroups,
  useProducts,
  useSyncNomenclature,
} from '@/hooks/use-menu'
import type { ProductType } from '@/types/menu'
import { KNOWN_IIKO_SOURCES, iikoSourceLabel } from '@/lib/iiko-sources'
import { formatCurrency } from '@/lib/formatters'

const ALL = '__all__'
const PAGE_SIZE = 100

const TYPE_LABELS: Record<ProductType, string> = {
  DISH: 'Блюдо',
  GOODS: 'Товар',
  MODIFIER: 'Модификатор',
  PREPARED: 'Полуфабрикат',
  SERVICE: 'Услуга',
}

const TYPE_OPTIONS: ProductType[] = ['DISH', 'GOODS', 'MODIFIER', 'PREPARED', 'SERVICE']

function fmtPrice(value: string | null): string {
  if (!value) return '—'
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return '—'
  return formatCurrency(n)
}

export function MenuProductsPage() {
  const [source, setSource] = useState(ALL)
  const [groupId, setGroupId] = useState(ALL)
  const [categoryId, setCategoryId] = useState(ALL)
  const [type, setType] = useState<ProductType | typeof ALL>(ALL)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const filters = useMemo(
    () => ({
      search: search.trim() || undefined,
      iiko_source_domain: source === ALL ? undefined : source,
      group_id: groupId === ALL ? undefined : Number(groupId),
      category_id: categoryId === ALL ? undefined : Number(categoryId),
      type: type === ALL ? undefined : (type as ProductType),
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [search, source, groupId, categoryId, type, page],
  )

  const { data: products = [], isLoading, error } = useProducts(filters)
  const groups = useNomenclatureGroups(source === ALL ? undefined : source)
  const categories = useNomenclatureCategories(source === ALL ? undefined : source)
  const syncMutation = useSyncNomenclature()

  const onSync = async () => {
    try {
      await syncMutation.mutateAsync()
    } catch {
      /* error rendered via mutation state below */
    }
  }

  const handleFilterChange = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v)
    setPage(0)
  }

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Номенклатура</h2>
          <p className="text-sm text-muted-foreground">
            Полный каталог iiko: блюда, товары, модификаторы, полуфабрикаты
          </p>
        </div>
        <Button
          variant="outline"
          onClick={onSync}
          disabled={syncMutation.isPending}
          title="Синхронизировать каталог из iiko"
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`}
          />
          {syncMutation.isPending ? 'Синхронизация…' : 'Синхронизация'}
        </Button>
      </div>

      {syncMutation.data && (
        <Card>
          <CardContent className="p-3 text-sm">
            <span className="font-medium">Синхронизация:</span>{' '}
            {syncMutation.data.total_categories} категорий ·{' '}
            {syncMutation.data.total_groups} групп ·{' '}
            {syncMutation.data.total_products} продуктов из{' '}
            {syncMutation.data.per_domain.length} источников
            {syncMutation.data.errors.length > 0 && (
              <span className="ml-2 text-destructive">
                ({syncMutation.data.errors.length} ошибок)
              </span>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs uppercase text-muted-foreground">Источник iiko</Label>
              <Select value={source} onValueChange={handleFilterChange(setSource)}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все источники</SelectItem>
                  {KNOWN_IIKO_SOURCES.map((host) => (
                    <SelectItem key={host} value={host}>
                      {iikoSourceLabel(host)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs uppercase text-muted-foreground">Тип</Label>
              <Select
                value={type}
                onValueChange={(v) => {
                  setType(v as ProductType | typeof ALL)
                  setPage(0)
                }}
              >
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все типы</SelectItem>
                  {TYPE_OPTIONS.map((t) => (
                    <SelectItem key={t} value={t}>
                      {TYPE_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs uppercase text-muted-foreground">Категория</Label>
              <Select value={categoryId} onValueChange={handleFilterChange(setCategoryId)}>
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Все" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все категории</SelectItem>
                  {(categories.data ?? []).map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs uppercase text-muted-foreground">Группа</Label>
              <Select value={groupId} onValueChange={handleFilterChange(setGroupId)}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Все" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Все группы</SelectItem>
                  {(groups.data ?? []).map((g) => (
                    <SelectItem key={g.id} value={String(g.id)}>
                      {g.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 flex-1 min-w-[220px]">
              <Label className="text-xs uppercase text-muted-foreground">Поиск</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Поиск по названию"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(0)
                  }}
                  className="pl-9"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingSpinner />
      ) : products.length === 0 ? (
        <EmptyState text="Не найдено товаров с такими фильтрами" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[90px]">Код</TableHead>
                <TableHead>Название</TableHead>
                <TableHead>Тип</TableHead>
                <TableHead>Источник</TableHead>
                <TableHead className="text-right">Цена</TableHead>
                <TableHead className="text-right">Себестоимость</TableHead>
                <TableHead>Меню</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-xs">{p.code || '—'}</TableCell>
                  <TableCell className="font-medium">
                    <div>{p.name}</div>
                    {p.description && (
                      <div className="text-xs text-muted-foreground line-clamp-1">
                        {p.description}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{TYPE_LABELS[p.type] || p.type}</Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    <span title={p.iiko_source_domain}>
                      {iikoSourceLabel(p.iiko_source_domain)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {fmtPrice(p.default_sale_price)}
                  </TableCell>
                  <TableCell className="text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {fmtPrice(p.estimated_purchase_price)}
                  </TableCell>
                  <TableCell>
                    {p.is_included_in_menu ? (
                      <Badge variant="outline" className="border-green-500/40 text-green-700 dark:text-green-400">
                        в меню
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-muted-foreground">
                        нет
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-3 text-sm border-t">
            <span className="text-muted-foreground">
              Страница {page + 1} · показано {products.length}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                ←
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={products.length < PAGE_SIZE}
              >
                →
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
