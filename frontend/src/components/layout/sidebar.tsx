import { NavLink } from 'react-router-dom'
import {
  Building2, CalendarDays, Clock, TrendingUp, GitCompare, RefreshCw,
  UserRound, Users, Calculator, FileText, ClipboardList, Target,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navSections = [
  {
    label: 'СПРАВОЧНИКИ',
    items: [
      { path: '/departments', label: 'Подразделения', icon: Building2 },
      { path: '/employees', label: 'Сотрудники', icon: Users },
    ],
  },
  {
    label: 'ПРОДАЖИ',
    items: [
      { path: '/sales/daily', label: 'Продажи по дням', icon: CalendarDays },
      { path: '/sales/hourly', label: 'Продажи по часам', icon: Clock },
      { path: '/sales/waiters', label: 'Продажи по официантам', icon: UserRound },
    ],
  },
  {
    label: 'ПРОГНОЗ ПРОДАЖ',
    items: [
      { path: '/forecast/branches', label: 'Прогноз по филиалам', icon: TrendingUp },
      { path: '/forecast/comparison', label: 'Сравнение факт / прогноз', icon: GitCompare },
    ],
  },
  {
    label: 'БОНУСЫ',
    items: [
      { path: '/bonus/calculations', label: 'Расчёты бонусов', icon: Calculator },
      { path: '/bonus/schemes', label: 'Схемы расчёта', icon: FileText },
      { path: '/bonus/manual-kpi', label: 'Ручной ввод KPI', icon: ClipboardList },
      { path: '/bonus/monthly-plans', label: 'Помесячные планы', icon: Target },
    ],
  },
  {
    label: 'СЕРВИС',
    items: [
      { path: '/sync', label: 'Синхронизация данных', icon: RefreshCw },
    ],
  },
]

export function Sidebar() {
  return (
    <aside className="w-64 min-h-screen bg-sidebar text-sidebar-foreground flex flex-col shrink-0">
      <div className="p-4 border-b border-sidebar-accent">
        <h1 className="text-lg font-bold">Sales Forecast</h1>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.label} className="mb-2">
            <div className="px-4 py-2 text-xs font-semibold text-sidebar-foreground/50 uppercase tracking-wider">
              {section.label}
            </div>
            {section.items.map((item) => (
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
        ))}
      </nav>
    </aside>
  )
}
