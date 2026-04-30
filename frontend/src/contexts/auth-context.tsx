import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  api,
  getSessionToken,
  setSessionExpiredHandler,
  setSessionToken,
} from '@/lib/api-client'
import type { AppUser, LoginResponse, SectionKey } from '@/types/auth'

interface AuthState {
  status: 'loading' | 'unauthenticated' | 'authenticated'
  user: AppUser | null
  error: string | null
}

interface AuthContextValue extends AuthState {
  login: (phone: string) => Promise<void>
  logout: () => Promise<void>
  hasSection: (section: SectionKey) => boolean
  isAdmin: boolean
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: getSessionToken() ? 'loading' : 'unauthenticated',
    user: null,
    error: null,
  })
  const expiredOnceRef = useRef(false)

  const fetchMe = useCallback(async () => {
    try {
      const data = await api.get<{ user: AppUser }>('/api/auth/me')
      setState({ status: 'authenticated', user: data.user, error: null })
    } catch {
      setSessionToken(null)
      setState({ status: 'unauthenticated', user: null, error: null })
    }
  }, [])

  useEffect(() => {
    if (getSessionToken()) {
      void fetchMe()
    }
  }, [fetchMe])

  useEffect(() => {
    setSessionExpiredHandler(() => {
      if (expiredOnceRef.current) return
      expiredOnceRef.current = true
      setState({ status: 'unauthenticated', user: null, error: 'Сессия истекла, войдите заново' })
    })
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (phone: string) => {
    setState((s) => ({ ...s, error: null }))
    try {
      const res = await api.post<LoginResponse>('/api/auth/login', { phone })
      setSessionToken(res.session_token)
      expiredOnceRef.current = false
      setState({ status: 'authenticated', user: res.user, error: null })
    } catch (err) {
      const detail = (err as { detail?: string })?.detail ?? 'Ошибка входа'
      setState({ status: 'unauthenticated', user: null, error: detail })
      throw err
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } catch {
      // ignore — we still clear local state
    }
    setSessionToken(null)
    setState({ status: 'unauthenticated', user: null, error: null })
  }, [])

  const value = useMemo<AuthContextValue>(() => {
    const sections = new Set(state.user?.allowed_sections ?? [])
    return {
      ...state,
      login,
      logout,
      refresh: fetchMe,
      isAdmin: state.user?.role_code === 'admin',
      hasSection: (s: SectionKey) => sections.has(s),
    }
  }, [state, login, logout, fetchMe])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
