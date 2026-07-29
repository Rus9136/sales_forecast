import { Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth-context'
import type { SectionKey } from '@/types/auth'

const SECTION_TO_PATH: Record<SectionKey, string> = {
  'dashboard': '/dashboard',
  'departments': '/departments',
  'employees': '/employees',
  'sales.daily': '/sales/daily',
  'sales.hourly': '/sales/hourly',
  'sales.waiters': '/sales/waiters',
  'forecast.branches': '/forecast/branches',
  'forecast.comparison': '/forecast/comparison',
  'forecast.sku': '/forecast/sku',
  'menu.products': '/menu/products',
  'menu.groups': '/menu/groups',
  'receipts.list': '/receipts',
  'receipts.stats': '/receipts/stats',
  'inventory.writeoffs': '/inventory/writeoffs',
  'inventory.order': '/inventory/order',
  'ai.recommendations': '/ai-recommendations',
  'pricing.dashboard': '/pricing/dashboard',
  'pricing.recommendations': '/pricing/recommendations',
  'pricing.rules': '/pricing/rules',
  'pricing.position_detail': '/pricing/dashboard',
  'pricing.outcomes': '/pricing/outcomes',
  'pricing.analytics': '/pricing/menu-roles',
  'pricing.reports': '/pricing/reports',
  'sync': '/sync',
  'users': '/users',
  'roles': '/roles',
}

const PRIORITY: SectionKey[] = [
  'dashboard',
  'departments', 'sales.daily', 'sales.hourly', 'sales.waiters',
  'forecast.branches', 'forecast.comparison',
  'pricing.dashboard', 'pricing.recommendations',
  'menu.products', 'menu.groups',
  'receipts.list', 'receipts.stats',
  'inventory.writeoffs', 'inventory.order',
  'ai.recommendations', 'employees',
  'pricing.rules', 'pricing.outcomes', 'pricing.analytics', 'pricing.reports', 'pricing.position_detail',
  'sync', 'users', 'roles',
]

export function HomeRedirect() {
  const { user } = useAuth()
  const allowed = new Set(user?.allowed_sections ?? [])
  const target = PRIORITY.find((s) => allowed.has(s))
  if (!target) return <Navigate to="/forbidden" replace />
  return <Navigate to={SECTION_TO_PATH[target]} replace />
}
