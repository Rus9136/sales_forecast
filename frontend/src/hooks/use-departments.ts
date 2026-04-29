import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { Department, DepartmentCreate, DepartmentUpdate } from '@/types/department'

export function useDepartments(showAllTypes = true) {
  return useQuery({
    queryKey: ['departments', { showAllTypes }],
    queryFn: () =>
      api.get<Department[]>('/api/departments/', {
        show_all_types: String(showAllTypes),
        limit: '10000',
      }),
  })
}

export function useCreateDepartment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: DepartmentCreate) =>
      api.post<Department>('/api/departments/', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['departments'] }),
  })
}

export function useUpdateDepartment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DepartmentUpdate }) =>
      api.put<Department>(`/api/departments/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['departments'] }),
  })
}

export function useDeleteDepartment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/departments/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['departments'] }),
  })
}

export function useSyncDepartments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/departments/sync'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['departments'] }),
  })
}
