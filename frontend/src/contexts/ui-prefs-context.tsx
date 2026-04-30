import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark'
export type AccentMode = 'emerald' | 'indigo' | 'amber' | 'slate'
export type DensityMode = 'compact' | 'cozy' | 'spacious'

interface UIPrefs {
  theme: ThemeMode
  accent: AccentMode
  density: DensityMode
  sidebarCollapsed: boolean
}

interface UIPrefsContextValue extends UIPrefs {
  setTheme: (v: ThemeMode) => void
  setAccent: (v: AccentMode) => void
  setDensity: (v: DensityMode) => void
  setSidebarCollapsed: (v: boolean | ((prev: boolean) => boolean)) => void
  toggleTheme: () => void
  toggleSidebar: () => void
}

const STORAGE_KEY = 'sf.ui-prefs'

const DEFAULT_PREFS: UIPrefs = {
  theme: 'light',
  accent: 'emerald',
  density: 'cozy',
  sidebarCollapsed: false,
}

function loadPrefs(): UIPrefs {
  if (typeof window === 'undefined') return DEFAULT_PREFS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_PREFS
    const parsed = JSON.parse(raw) as Partial<UIPrefs>
    return { ...DEFAULT_PREFS, ...parsed }
  } catch {
    return DEFAULT_PREFS
  }
}

function savePrefs(prefs: UIPrefs) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // ignore quota / private mode errors
  }
}

const UIPrefsContext = createContext<UIPrefsContextValue | null>(null)

export function UIPrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<UIPrefs>(() => loadPrefs())

  useEffect(() => {
    const html = document.documentElement
    html.setAttribute('data-theme', prefs.theme)
    html.setAttribute('data-accent', prefs.accent)
    html.setAttribute('data-density', prefs.density)
    html.setAttribute('data-sidebar', prefs.sidebarCollapsed ? 'collapsed' : 'expanded')
    savePrefs(prefs)
  }, [prefs])

  const setTheme = useCallback((theme: ThemeMode) => setPrefs((p) => ({ ...p, theme })), [])
  const setAccent = useCallback((accent: AccentMode) => setPrefs((p) => ({ ...p, accent })), [])
  const setDensity = useCallback((density: DensityMode) => setPrefs((p) => ({ ...p, density })), [])
  const setSidebarCollapsed = useCallback(
    (v: boolean | ((prev: boolean) => boolean)) =>
      setPrefs((p) => ({
        ...p,
        sidebarCollapsed: typeof v === 'function' ? v(p.sidebarCollapsed) : v,
      })),
    [],
  )
  const toggleTheme = useCallback(
    () => setPrefs((p) => ({ ...p, theme: p.theme === 'dark' ? 'light' : 'dark' })),
    [],
  )
  const toggleSidebar = useCallback(
    () => setPrefs((p) => ({ ...p, sidebarCollapsed: !p.sidebarCollapsed })),
    [],
  )

  const value = useMemo<UIPrefsContextValue>(
    () => ({
      ...prefs,
      setTheme,
      setAccent,
      setDensity,
      setSidebarCollapsed,
      toggleTheme,
      toggleSidebar,
    }),
    [prefs, setTheme, setAccent, setDensity, setSidebarCollapsed, toggleTheme, toggleSidebar],
  )

  return <UIPrefsContext.Provider value={value}>{children}</UIPrefsContext.Provider>
}

export function useUIPrefs(): UIPrefsContextValue {
  const ctx = useContext(UIPrefsContext)
  if (!ctx) throw new Error('useUIPrefs must be used inside UIPrefsProvider')
  return ctx
}
