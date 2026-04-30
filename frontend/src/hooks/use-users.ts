import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { AppUser, UserCreatePayload, UserUpdatePayload } from '@/types/auth'

export function useUsers() {
  return useQuery({
    queryKey: ['app-users'],
    queryFn: () => api.get<AppUser[]>('/api/users/'),
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UserCreatePayload) => api.post<AppUser>('/api/users/', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-users'] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UserUpdatePayload }) =>
      api.put<AppUser>(`/api/users/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-users'] }),
  })
}

export function useDeleteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-users'] }),
  })
}
