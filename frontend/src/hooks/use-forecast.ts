import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { BatchForecast, ForecastComparison } from '@/types/forecast'

interface ForecastParams {
  from_date?: string
  to_date?: string
  department_id?: string
}

export function useBatchForecasts(params: ForecastParams) {
  return useQuery({
    queryKey: ['forecast', 'batch', params],
    queryFn: () =>
      api.get<BatchForecast[]>('/api/forecast/batch', {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
      }),
    enabled: !!params.from_date && !!params.to_date,
  })
}

export function useForecastComparison(params: ForecastParams) {
  return useQuery({
    queryKey: ['forecast', 'comparison', params],
    queryFn: () =>
      api.get<ForecastComparison[]>('/api/forecast/comparison', {
        from_date: params.from_date,
        to_date: params.to_date,
        department_id: params.department_id,
      }),
    enabled: !!params.from_date && !!params.to_date,
  })
}

export function useRetrainModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/forecast/retrain'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['forecast'] }),
  })
}
