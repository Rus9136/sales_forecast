import { NavLink } from 'react-router-dom'
import {
  Building2, CalendarDays, Clock, TrendingUp, GitCompare, RefreshCw,
  UserRound, Users, Calculator, FileText, ClipboardList, Target, Sparkles,
  Shield, UserCog, LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import type { SectionKey } from '@/types/auth'

interface NavItem {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  section: SectionKey
}

interface NavSection {
  label: string
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    label: 'СПРАВОЧНИКИ',
    items: [
      { path: '/departments', label: 'Подразделения', icon: Building2, section: 'departments' },
      { path: '/employees', label: 'Сотрудники', icon: Users, section: 'employees' },
    ],
  },
  {
    label: 'ПРОДАЖИ',
    items: [
      { path: '/sales/daily', label: 'Продажи по дням', icon: CalendarDays, section: 'sales.daily' },
      { path: '/sales/hourly', label: 'Продажи по часам', icon: Clock, section: 'sales.hourly' },
      { path: '/sales/waiters', label: 'Продажи по официантам', icon: UserRound, section: 'sales.waiters' },
    ],
  },
  {
    label: 'ПРОГНОЗ ПРОДАЖ',
    items: [
      { path: '/forecast/branches', label: 'Прогноз по филиалам', icon: TrendingUp, section: 'forecast.branches' },
      { path: '/forecast/comparison', label: 'Сравнение факт / прогноз', icon: GitCompare, section: 'forecast.comparison' },
    ],
  },
  {
    label: 'БОНУСЫ',
    items: [
      { path: '/bonus/calculations', label: 'Расчёты бонусов', icon: Calculator, section: 'bonus.calculations' },
      { path: '/bonus/schemes', label: 'Схемы расчёта', icon: FileText, section: 'bonus.schemes' },
      { path: '/bonus/manual-kpi', label: 'Ручной ввод KPI', icon: ClipboardList, section: 'bonus.manual-kpi' },
      { path: '/bonus/monthly-plans', label: 'Помесячные планы', icon: Target, section: 'bonus.monthly-plans' },
    ],
  },
  {
    label: 'AI АНАЛИТИКА',
    items: [
      { path: '/ai-recommendations', label: 'Рекомендации ИИ', icon: Sparkles, section: 'ai.recommendations' },
    ],
  },
  {
    label: 'СЕРВИС',
    items: [
      { path: '/sync', label: 'Синхронизация данных', icon: RefreshCw, section: 'sync' },
    ],
  },
  {
    label: 'АДМИНИСТРИРОВАНИЕ',
    items: [
      { path: '/users', label: 'Пользователи', icon: UserCog, section: 'users' },
      { path: '/roles', label: 'Роли и доступы', icon: Shield, section: 'roles' },
    ],
  },
]

export function Sidebar() {
  const { user, hasSection, logout } = useAuth()

  return (
    <aside className="w-64 min-h-screen bg-sidebar text-sidebar-foreground flex flex-col shrink-0">
      <div className="p-4 border-b border-sidebar-accent">
        <h1 className="text-lg font-bold">Sales Forecast</h1>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navSections.map((section) => {
          const visibleItems = section.items.filter((i) => hasSection(i.section))
          if (visibleItems.length === 0) return null
          return (
            <div key={section.label} className="mb-2">
              <div className="px-4 py-2 text-xs font-semibold text-sidebar-foreground/50 uppercase tracking-wider">
                {section.label}
              </div>
              {visibleItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors',
                      isActive
                        ? 'bg-sidebar-accent text-white font-medium'
                        : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
                    )
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>
      {user && (
        <div className="border-t border-sidebar-accent p-4 space-y-2">
          <div className="text-sm font-medium text-sidebar-foreground/90 truncate">
            {user.full_name || user.phone}
          </div>
          <div className="text-xs text-sidebar-foreground/60">
            {user.role_name || user.role_code} · {user.phone}
          </div>
          <button
            type="button"
            onClick={() => { void logout() }}
            className="flex items-center gap-2 text-xs text-sidebar-foreground/70 hover:text-sidebar-foreground transition-colors"
          >
            <LogOut className="h-3 w-3" />
            Выйти
          </button>
        </div>
      )}
    </aside>
  )
}
