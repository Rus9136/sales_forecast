import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

/** Sentinel «Все подразделения» — совпадает с DepartmentSelect. */
export const ALL_DEPARTMENTS = '__all__'

const STORAGE_KEY = 'sf.pricing.department'

interface PricingContextValue {
  /** Выбранная точка ('__all__' = вся сеть). Общая для всех вкладок ценообразования. */
  departmentId: string
  setDepartmentId: (id: string) => void
  /** undefined когда выбрана вся сеть — удобно для API-параметров. */
  effectiveDepartmentId: string | undefined
}

const PricingContext = createContext<PricingContextValue | null>(null)

export function PricingProvider({ children }: { children: ReactNode }) {
  const [departmentId, setState] = useState<string>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) ?? ALL_DEPARTMENTS
    } catch {
      return ALL_DEPARTMENTS
    }
  })

  const setDepartmentId = useCallback((id: string) => {
    setState(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      /* private mode — не критично */
    }
  }, [])

  const value = useMemo<PricingContextValue>(
    () => ({
      departmentId,
      setDepartmentId,
      effectiveDepartmentId: departmentId === ALL_DEPARTMENTS ? undefined : departmentId,
    }),
    [departmentId, setDepartmentId],
  )

  return <PricingContext.Provider value={value}>{children}</PricingContext.Provider>
}

export function usePricingScope(): PricingContextValue {
  const ctx = useContext(PricingContext)
  if (!ctx) throw new Error('usePricingScope must be used within PricingProvider')
  return ctx
}
