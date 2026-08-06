import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom'

import { DepartmentSelect } from '@/components/shared/department-select'
import { usePricingScope } from '@/contexts/pricing-context'
import { useAuth } from '@/contexts/auth-context'
import { useRecommendationsSummary } from '@/hooks/use-pricing'
import type { SectionKey } from '@/types/auth'

interface PricingSubTab {
  path: string
  label: string
  section: SectionKey
}

interface PricingTab {
  /** Основная вкладка. path = путь первой под-вкладки (или собственный). */
  label: string
  children: PricingSubTab[]
}

/** Структура вкладок workspace: порядок = порядок рабочего цикла менеджера. */
export const PRICING_TABS: PricingTab[] = [
  {
    label: 'Обзор',
    children: [{ path: '/pricing/dashboard', label: 'Обзор', section: 'pricing.dashboard' }],
  },
  {
    label: 'Рекомендации',
    children: [
      { path: '/pricing/recommendations', label: 'Рекомендации', section: 'pricing.recommendations' },
      { path: '/pricing/orders', label: 'Приказы в iiko', section: 'pricing.apply' },
    ],
  },
  // Временно скрыто (роуты/страницы сохранены — открыть = раскомментировать):
  // {
  //   label: 'Результаты',
  //   children: [
  //     { path: '/pricing/outcomes', label: 'Эффект цен', section: 'pricing.outcomes' },
  //     { path: '/pricing/reports', label: 'Отчёты ИИ', section: 'pricing.reports' },
  //   ],
  // },
  {
    label: 'Аналитика',
    children: [
      { path: '/pricing/menu-roles', label: 'Роли меню', section: 'pricing.analytics' },
      { path: '/pricing/elasticity', label: 'Чувствительность спроса', section: 'pricing.analytics' },
    ],
  },
  {
    label: 'Настройки',
    children: [
      { path: '/pricing/rules', label: 'Правила', section: 'pricing.rules' },
      { path: '/pricing/audit', label: 'Журнал действий', section: 'pricing.analytics' },
    ],
  },
]

/** Плоский список для CmdK-поиска. */
export const PRICING_NAV_ITEMS: PricingSubTab[] = PRICING_TABS.flatMap((t) =>
  t.children.map((c) => ({ ...c, label: t.label === c.label ? c.label : `${t.label} · ${c.label}` })),
)

export function PricingLayout() {
  const location = useLocation()
  const { hasSection } = useAuth()
  const { departmentId, setDepartmentId, effectiveDepartmentId } = usePricingScope()

  const canRecs = hasSection('pricing.recommendations')
  const summary = useRecommendationsSummary(effectiveDepartmentId, { enabled: canRecs })
  const newCount = summary.data?.by_status?.new ?? 0

  const visibleTabs = PRICING_TABS.map((t) => ({
    ...t,
    children: t.children.filter((c) => hasSection(c.section)),
  })).filter((t) => t.children.length > 0)

  const activeTab = visibleTabs.find((t) =>
    t.children.some((c) => location.pathname.startsWith(c.path)),
  )

  return (
    <div className="page">
      <div className="pricing-ws__head">
        <div className="page__title">
          <h1>Ценообразование</h1>
          <span className="sub">
            Система предлагает цены каждую ночь в 05:00 · вы утверждаете · через 14 дней виден эффект
          </span>
        </div>
        <div className="page__actions">
          <DepartmentSelect
            value={departmentId}
            onChange={setDepartmentId}
            includeInactive
            label="Точка (общая для всех вкладок)"
          />
        </div>
      </div>

      <nav className="pricing-tabs" aria-label="Разделы ценообразования">
        {visibleTabs.map((t) => {
          const isActive = activeTab?.label === t.label
          return (
            <NavLink
              key={t.label}
              to={t.children[0].path}
              className={'pricing-tab' + (isActive ? ' active' : '')}
            >
              {t.label}
              {t.label === 'Рекомендации' && newCount > 0 && (
                <span className="cnt">{newCount.toLocaleString('ru-RU')}</span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {activeTab && activeTab.children.length > 1 && (
        <div className="pricing-subtabs" role="tablist">
          {activeTab.children.map((c) => (
            <NavLink
              key={c.path}
              to={c.path}
              className={
                'pricing-subtab' + (location.pathname.startsWith(c.path) ? ' active' : '')
              }
            >
              {c.label}
            </NavLink>
          ))}
        </div>
      )}

      <div className="pricing-body">
        <Outlet />
      </div>
    </div>
  )
}

/** /pricing → первая доступная вкладка (по правам роли). */
export function PricingHomeRedirect() {
  const { hasSection } = useAuth()
  const first = PRICING_TABS.flatMap((t) => t.children).find((c) => hasSection(c.section))
  return <Navigate to={first?.path ?? '/forbidden'} replace />
}
