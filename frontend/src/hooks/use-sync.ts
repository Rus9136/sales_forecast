import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { SyncStatusResponse } from '@/types/sync'
import type { SyncResult } from '@/types/sales'

export type { SyncResult }

export function useAutoSyncStatus() {
  return useQuery({
    queryKey: ['sync', 'status'],
    queryFn: () => api.get<SyncStatusResponse>('/api/sales/auto-sync/status'),
  })
}

export function useSyncSales() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: { from_date: string; to_date: string; department_id?: string }) =>
      api.post<SyncResult>(
        '/api/sales/sync',
        undefined,
        {
          from_date: params.from_date,
          to_date: params.to_date,
          department_id: params.department_id,
        },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync'] })
      qc.invalidateQueries({ queryKey: ['sales'] })
    },
  })
}

export function useTestAutoSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/sales/auto-sync/test'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync'] }),
  })
}
