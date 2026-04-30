import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/auth-context'
import type { SectionKey } from '@/types/auth'

interface ProtectedRouteProps {
  /** If set, requires this section to be present in the user's allowed_sections */
  section?: SectionKey
}

export function ProtectedRoute({ section }: ProtectedRouteProps) {
  const { status, hasSection } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        Загрузка...
      </div>
    )
  }
  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (section && !hasSection(section)) {
    return <Navigate to="/forbidden" replace />
  }
  return <Outlet />
}
