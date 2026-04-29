import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { SalesByWaiter, WaiterSyncResult } from '@/types/waiter'

export { useEmployees, useSyncEmployees } from './use-employees'

interface WaiterSalesParams {
  from_date?: string
  to_date?: string
  department_id?: string
  employee_id?: string
  waiter_name?: string
}

export function useWaiterSales(params: WaiterSalesParams) {
  return useQuery({
    queryKey: ['sales', 'by-waiter', params],
    queryFn: () =>
      api.get<SalesByWaiter[]>('/api/sales/by-waiter', {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
        employee_id: params.employee_id,
        waiter_name: params.waiter_name,
        limit: '5000',
      }),
    enabled: !!params.from_date && !!params.to_date,
  })
}

export function useSyncWaiterSales() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: { from_date?: string; to_date?: string; department_id?: string }) =>
      api.post<WaiterSyncResult>('/api/sales/sync-waiters', undefined, {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sales', 'by-waiter'] })
    },
  })
}

