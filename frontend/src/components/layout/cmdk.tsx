import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useAuth } from '@/contexts/auth-context'
import { navSections } from './sidebar'

interface CmdKProps {
  open: boolean
  onClose: () => void
}

export function CmdK({ open, onClose }: CmdKProps) {
  const navigate = useNavigate()
  const { hasSection } = useAuth()
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const norm = q.trim().toLowerCase()
    const flat = navSections.flatMap((g) =>
      g.items
        .filter((it) => hasSection(it.section))
        .map((it) => ({ ...it, group: g.label })),
    )
    if (!norm) return flat
    return flat.filter(
      (it) =>
        it.label.toLowerCase().includes(norm) || it.group.toLowerCase().includes(norm),
    )
  }, [q, hasSection])

  useEffect(() => {
    if (open) {
      setQ('')
      setSel(0)
      const id = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(id)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSel((s) => Math.min(filtered.length - 1, s + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSel((s) => Math.max(0, s - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const it = filtered[sel]
        if (it) {
          navigate(it.path)
          onClose()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, filtered, sel, onClose, navigate])

  if (!open) return null

  // Group filtered items by group while preserving global indices for arrow-key selection
  const grouped: Record<string, Array<{ id: string; label: string; group: string; path: string; index: number }>> = {}
  filtered.forEach((it, i) => {
    const groupItems = grouped[it.group] || (grouped[it.group] = [])
    groupItems.push({ id: it.path, label: it.label, group: it.group, path: it.path, index: i })
  })

  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <div className="cmdk__input">
          <Search size={16} style={{ color: 'var(--text-muted)' }} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setSel(0)
            }}
            placeholder="Перейти к разделу, найти филиал, сотрудника…"
          />
          <span className="kbd">ESC</span>
        </div>
        <div className="cmdk__list">
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Ничего не найдено
            </div>
          )}
          {Object.entries(grouped).map(([groupLabel, items]) => (
            <div key={groupLabel}>
              <div className="cmdk__group-title">{groupLabel}</div>
              {items.map((it) => (
                <div
                  key={it.id}
                  className={'cmdk__item' + (it.index === sel ? ' selected' : '')}
                  onMouseEnter={() => setSel(it.index)}
                  onClick={() => {
                    navigate(it.path)
                    onClose()
                  }}
                >
                  <span>{it.label}</span>
                  <span className="desc">Перейти →</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
