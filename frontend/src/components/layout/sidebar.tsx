import { NavLink } from 'react-router-dom'
import {
  Building2, CalendarDays, Clock, TrendingUp, GitCompare, RefreshCw,
  UserRound, Users, Sparkles, BookOpen, FolderTree, Receipt, BarChart3,
  Shield, UserCog, LogOut, Settings, LayoutDashboard, UtensilsCrossed,
  BadgePercent, Tags, SlidersHorizontal, Target, Activity, Boxes, ScrollText,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import type { SectionKey } from '@/types/auth'

export interface NavItem {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  section: SectionKey
  count?: number
}

export interface NavSection {
  label: string
  items: NavItem[]
}

export const navSections: NavSection[] = [
  {
    label: 'Обзор',
    items: [
      { path: '/dashboard', label: 'Дашборд', icon: LayoutDashboard, section: 'dashboard' },
    ],
  },
  {
    label: 'Аналитика',
    items: [
      { path: '/ai-recommendations', label: 'Рекомендации ИИ', icon: Sparkles, section: 'ai.recommendations' },
    ],
  },
  {
    label: 'Продажи',
    items: [
      { path: '/sales/daily', label: 'Продажи по дням', icon: CalendarDays, section: 'sales.daily' },
      { path: '/sales/hourly', label: 'Продажи по часам', icon: Clock, section: 'sales.hourly' },
      { path: '/sales/waiters', label: 'Продажи по официантам', icon: UserRound, section: 'sales.waiters' },
    ],
  },
  {
    label: 'Прогноз продаж',
    items: [
      { path: '/forecast/branches', label: 'Прогноз по филиалам', icon: TrendingUp, section: 'forecast.branches' },
      { path: '/forecast/comparison', label: 'Сравнение факт / прогноз', icon: GitCompare, section: 'forecast.comparison' },
      { path: '/forecast/sku', label: 'Прогноз по блюдам', icon: UtensilsCrossed, section: 'forecast.sku' },
    ],
  },
  {
    label: 'Ценообразование',
    items: [
      { path: '/pricing/dashboard', label: 'Дашборд цен', icon: BadgePercent, section: 'pricing.dashboard' },
      { path: '/pricing/recommendations', label: 'Рекомендации цен', icon: Tags, section: 'pricing.recommendations' },
      { path: '/pricing/rules', label: 'Правила цен', icon: SlidersHorizontal, section: 'pricing.rules' },
      { path: '/pricing/outcomes', label: 'Результаты пилота', icon: Target, section: 'pricing.outcomes' },
      { path: '/pricing/elasticity', label: 'Эластичность', icon: Activity, section: 'pricing.analytics' },
      { path: '/pricing/menu-roles', label: 'Роли меню', icon: Boxes, section: 'pricing.analytics' },
      { path: '/pricing/audit', label: 'Журнал действий', icon: ScrollText, section: 'pricing.analytics' },
    ],
  },
  {
    label: 'Меню',
    items: [
      { path: '/menu/products', label: 'Номенклатура', icon: BookOpen, section: 'menu.products' },
      { path: '/menu/groups', label: 'Группы', icon: FolderTree, section: 'menu.groups' },
    ],
  },
  {
    label: 'Чеки',
    items: [
      { path: '/receipts', label: 'Журнал чеков', icon: Receipt, section: 'receipts.list' },
      { path: '/receipts/stats', label: 'Продажи по блюдам', icon: BarChart3, section: 'receipts.stats' },
    ],
  },
  {
    label: 'Справочники',
    items: [
      { path: '/departments', label: 'Подразделения', icon: Building2, section: 'departments' },
      { path: '/employees', label: 'Сотрудники', icon: Users, section: 'employees' },
    ],
  },
  {
    label: 'Сервис',
    items: [
      { path: '/sync', label: 'Синхронизация данных', icon: RefreshCw, section: 'sync' },
    ],
  },
  {
    label: 'Администрирование',
    items: [
      { path: '/users', label: 'Пользователи', icon: UserCog, section: 'users' },
      { path: '/roles', label: 'Роли и доступы', icon: Shield, section: 'roles' },
    ],
  },
]

function initials(name: string | null | undefined, phone: string | undefined): string {
  if (name) {
    const parts = name.trim().split(/\s+/).filter(Boolean)
    if (parts.length === 0) return '—'
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return phone ? phone.slice(-2) : '—'
}

export function Sidebar() {
  const { user, hasSection, logout } = useAuth()

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="logo">Sf</span>
        <div className="brand-text">
          <b>Sales Forecast</b>
          <span>Aqniet Holding</span>
        </div>
      </div>

      <nav style={{ flex: 1, overflowY: 'auto', padding: '0 0 8px' }}>
        {navSections.map((section) => {
          const visibleItems = section.items.filter((i) => hasSection(i.section))
          if (visibleItems.length === 0) return null
          return (
            <div key={section.label} className="sidebar__group">
              <div className="sidebar__group-title">{section.label}</div>
              {visibleItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  title={item.label}
                  className={({ isActive }) => cn('nav-item', isActive && 'active')}
                >
                  <item.icon className="icon" />
                  <span className="label">{item.label}</span>
                  {item.count != null && (
                    <span className="count">{item.count.toLocaleString('ru-RU')}</span>
                  )}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>

      {user && (
        <div className="sidebar__footer">
          <span className="avatar">{initials(user.full_name, user.phone)}</span>
          <div className="meta">
            <b>{user.full_name || user.phone}</b>
            <span>{user.role_name || user.role_code}</span>
          </div>
          <button
            type="button"
            onClick={() => { void logout() }}
            className="btn-ghost btn-icon btn-icon-sm footer-action"
            title="Выйти"
          >
            <LogOut size={14} />
          </button>
          <button
            type="button"
            className="btn-ghost btn-icon btn-icon-sm footer-action"
            title="Настройки"
            disabled
            style={{ opacity: 0.5 }}
          >
            <Settings size={14} />
          </button>
        </div>
      )}
    </aside>
  )
}
