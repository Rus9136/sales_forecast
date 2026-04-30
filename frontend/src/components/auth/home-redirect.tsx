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
  'bonus.calculations': '/bonus/calculations',
  'bonus.schemes': '/bonus/schemes',
  'bonus.manual-kpi': '/bonus/manual-kpi',
  'bonus.monthly-plans': '/bonus/monthly-plans',
  'ai.recommendations': '/ai-recommendations',
  'sync': '/sync',
  'users': '/users',
  'roles': '/roles',
}

const PRIORITY: SectionKey[] = [
  'dashboard',
  'departments', 'sales.daily', 'sales.hourly', 'sales.waiters',
  'forecast.branches', 'forecast.comparison',
  'bonus.calculations', 'bonus.schemes', 'bonus.manual-kpi', 'bonus.monthly-plans',
  'ai.recommendations', 'employees', 'sync', 'users', 'roles',
]

export function HomeRedirect() {
  const { user } = useAuth()
  const allowed = new Set(user?.allowed_sections ?? [])
  const target = PRIORITY.find((s) => allowed.has(s))
  if (!target) return <Navigate to="/forbidden" replace />
  return <Navigate to={SECTION_TO_PATH[target]} replace />
}
