import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { useProducts } from '@/hooks/use-menu'
import type { Product } from '@/types/menu'

interface ProductSearchProps {
  /** Выбранный продукт (null — не выбран). */
  value: Product | null
  onChange: (p: Product | null) => void
  placeholder?: string
}

/**
 * Комбобокс поиска блюда по названию — вместо ручного ввода числового ID.
 * Ищет по каталогу номенклатуры (только DISH/GOODS, без удалённых).
 */
export function ProductSearch({ value, onChange, placeholder = 'Начните вводить название…' }: ProductSearchProps) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 300)
    return () => clearTimeout(id)
  }, [query])

  const products = useProducts(
    debounced.length >= 2 ? { search: debounced, limit: 10 } : { limit: 0 },
  )
  const items = (debounced.length >= 2 ? products.data ?? [] : []).filter(
    (p) => !p.is_deleted && (p.type === 'DISH' || p.type === 'GOODS'),
  )

  // Закрытие по клику вне
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  if (value) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{value.name}</span>
        <span className="text-xs text-muted-foreground">#{value.id}{value.code ? ` · код ${value.code}` : ''}</span>
        <button
          type="button"
          className="text-xs underline text-muted-foreground"
          onClick={() => { onChange(null); setQuery('') }}
        >
          изменить
        </button>
      </div>
    )
  }

  return (
    <div ref={rootRef} className="relative">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="pl-9"
        />
      </div>
      {open && debounced.length >= 2 && (
        <div
          className="absolute z-30 mt-1 w-full rounded-md border overflow-hidden"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)', boxShadow: 'var(--shadow-pop)' }}
        >
          {products.isLoading ? (
            <div className="p-3 text-sm text-muted-foreground">Поиск…</div>
          ) : items.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground">Ничего не найдено</div>
          ) : (
            items.map((p) => (
              <button
                key={p.id}
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-muted/60"
                onClick={() => { onChange(p); setOpen(false) }}
              >
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-muted-foreground ml-2">
                  #{p.id}{p.code ? ` · код ${p.code}` : ''}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
