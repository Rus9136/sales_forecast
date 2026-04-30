import { useLocation } from 'react-router-dom'
import { Bell, ChevronRight, Moon, PanelLeftClose, Search, Sun } from 'lucide-react'
import { useUIPrefs } from '@/contexts/ui-prefs-context'
import { navSections } from './sidebar'

interface TopbarProps {
  onOpenCmdK: () => void
}

function findCurrent(pathname: string) {
  for (const group of navSections) {
    for (const item of group.items) {
      if (pathname === item.path || pathname.startsWith(item.path + '/')) {
        return { group: group.label, label: item.label }
      }
    }
  }
  return null
}

export function Topbar({ onOpenCmdK }: TopbarProps) {
  const location = useLocation()
  const { theme, toggleTheme, toggleSidebar } = useUIPrefs()
  const current = findCurrent(location.pathname)

  return (
    <header className="topbar">
      <button
        type="button"
        className="btn-ghost btn-icon btn-icon-sm"
        onClick={toggleSidebar}
        title="Свернуть/развернуть"
      >
        <PanelLeftClose size={16} />
      </button>

      <div className="crumbs">
        <span>Aqniet</span>
        {current && (
          <>
            <ChevronRight size={11} className="sep" />
            <span>{current.group}</span>
            <ChevronRight size={11} className="sep" />
            <b>{current.label}</b>
          </>
        )}
      </div>

      <div className="spacer" />

      <div
        className="search-trigger topbar-search"
        onClick={onOpenCmdK}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onOpenCmdK()
          }
        }}
      >
        <Search size={14} style={{ color: 'var(--text-subtle)' }} />
        <input readOnly placeholder="Поиск по системе…" />
        <span className="kbd">⌘ K</span>
      </div>

      <div className="topbar-actions">
        <button type="button" className="btn-ghost btn-icon" title="Уведомления">
          <Bell size={16} />
          <span
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              width: 6,
              height: 6,
              background: 'var(--neg)',
              borderRadius: 999,
            }}
          />
        </button>
        <button
          type="button"
          className="btn-ghost btn-icon"
          onClick={toggleTheme}
          title="Сменить тему"
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}
