import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { AppRole, RolesResponse, SectionKey } from '@/types/auth'

export function useRoles() {
  return useQuery({
    queryKey: ['app-roles'],
    queryFn: () => api.get<RolesResponse>('/api/auth/roles'),
  })
}

interface UpdateRolePayload {
  code: string
  name?: string
  allowed_sections?: SectionKey[]
}

export function useUpdateRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ code, ...rest }: UpdateRolePayload) =>
      api.put<AppRole>(`/api/auth/roles/${code}`, rest),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['app-roles'] })
      qc.invalidateQueries({ queryKey: ['app-users'] })
    },
  })
}
