import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  SkuForecastRange,
  SkuTopNResponse,
  SkuModelInfo,
  SkuRetrainResponse,
} from '@/types/sku-forecast'

interface SkuBatchParams {
  department_id?: string
  from_date?: string
  to_date?: string
  top_n?: number
}

export function useSkuBatchForecasts(params: SkuBatchParams) {
  return useQuery({
    queryKey: ['forecast', 'sku', 'batch', params],
    queryFn: () =>
      api.get<SkuForecastRange>('/api/forecast/sku/batch', {
        department_id: params.department_id,
        from_date: params.from_date,
        to_date: params.to_date,
        top_n: params.top_n?.toString(),
      }),
    enabled:
      !!params.department_id &&
      params.department_id !== '__all__' &&
      !!params.from_date &&
      !!params.to_date,
  })
}

interface SkuTopNParams {
  department_id?: string
  period_days?: number
  n?: number
}

export function useSkuTopN(params: SkuTopNParams) {
  return useQuery({
    queryKey: ['forecast', 'sku', 'top-n', params],
    queryFn: () =>
      api.get<SkuTopNResponse>('/api/forecast/sku/top-n', {
        department_id: params.department_id,
        period_days: params.period_days?.toString(),
        n: params.n?.toString(),
      }),
  })
}

export function useSkuModelInfo() {
  return useQuery({
    queryKey: ['forecast', 'sku', 'model-info'],
    queryFn: () => api.get<SkuModelInfo>('/api/forecast/sku/model/info'),
  })
}

export function useSkuRetrainModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: { days?: number; active_window_days?: number }) =>
      api.post<SkuRetrainResponse>('/api/forecast/sku/retrain', body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['forecast', 'sku'] })
    },
  })
}
