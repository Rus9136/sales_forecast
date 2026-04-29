import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { Employee, EmployeesSyncResult } from '@/types/waiter'

export interface EmployeesFilters {
  search?: string
  role_code?: string
  department_code?: string
  include_deleted?: boolean
}

export function useEmployees(filters: EmployeesFilters | boolean = false) {
  // Backward-compat: useEmployees(true) means include_deleted = true.
  const f: EmployeesFilters =
    typeof filters === 'boolean' ? { include_deleted: filters } : filters

  return useQuery({
    queryKey: ['employees', f],
    queryFn: () =>
      api.get<Employee[]>('/api/employees/', {
        search: f.search,
        role_code: f.role_code,
        department_code: f.department_code,
        include_deleted: f.include_deleted ? 'true' : undefined,
        limit: '5000',
      }),
    staleTime: 5 * 60_000,
  })
}

export function useSyncEmployees() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<EmployeesSyncResult>('/api/employees/sync'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] })
    },
  })
}
