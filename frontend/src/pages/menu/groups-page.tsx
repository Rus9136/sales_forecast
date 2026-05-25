import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { useNomenclatureGroupsTree } from '@/hooks/use-menu'
import type { NomenclatureGroupTreeNode } from '@/types/menu'
import { KNOWN_IIKO_SOURCES, iikoSourceLabel } from '@/lib/iiko-sources'

const ALL = '__all__'

interface GroupNodeProps {
  node: NomenclatureGroupTreeNode
  depth: number
}

function GroupNode({ node, depth }: GroupNodeProps) {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 px-2 hover:bg-muted/50 rounded cursor-pointer"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )
        ) : (
          <span className="h-3.5 w-3.5 inline-block" />
        )}
        <span className="font-medium text-sm flex-1">{node.name}</span>
        {node.code && (
          <span className="text-xs font-mono text-muted-foreground">{node.code}</span>
        )}
        {hasChildren && (
          <Badge variant="secondary" className="text-xs">
            {node.children.length}
          </Badge>
        )}
      </div>
      {open && hasChildren && (
        <div>
          {node.children.map((c) => (
            <GroupNode key={c.id} node={c} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export function MenuGroupsPage() {
  const [source, setSource] = useState(ALL)
  const { data: tree = [], isLoading, error } = useNomenclatureGroupsTree(
    source === ALL ? undefined : source,
  )

  const totalCount = useMemo(() => {
    const count = (nodes: NomenclatureGroupTreeNode[]): number =>
      nodes.reduce((sum, n) => sum + 1 + count(n.children), 0)
    return count(tree)
  }, [tree])

  if (error) return <ErrorAlert message={(error as Error).message} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Группы номенклатуры</h2>
          <p className="text-sm text-muted-foreground">
            Иерархия групп iiko (Бар, Кухня, Барные модификаторы…)
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs uppercase text-muted-foreground">Источник iiko</Label>
              <Select value={source} onValueChange={setSource}>
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
            <div className="text-sm text-muted-foreground ml-auto">
              Всего групп: <span className="font-semibold">{totalCount}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingSpinner />
      ) : tree.length === 0 ? (
        <EmptyState text="Нет групп для выбранного источника" />
      ) : (
        <Card>
          <CardContent className="p-2">
            {tree.map((node) => (
              <GroupNode key={node.id} node={node} depth={0} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
