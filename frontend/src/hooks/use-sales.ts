import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { SalesSummary, SalesByHour } from '@/types/sales'

interface SalesParams {
  from_date?: string
  to_date?: string
  department_id?: string
}

interface HourlySalesParams extends SalesParams {
  hour?: string
}

export function useDailySales(params: SalesParams) {
  return useQuery({
    queryKey: ['sales', 'daily', params],
    queryFn: () =>
      api.get<SalesSummary[]>('/api/sales/summary', {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
        limit: '1000',
      }),
    enabled: !!params.from_date && !!params.to_date,
  })
}

export function useHourlySales(params: HourlySalesParams) {
  return useQuery({
    queryKey: ['sales', 'hourly', params],
    queryFn: () =>
      api.get<SalesByHour[]>('/api/sales/hourly', {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
        hour: params.hour,
        limit: '1000',
      }),
    enabled: !!params.from_date && !!params.to_date,
  })
}
