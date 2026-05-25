import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  Receipt,
  ReceiptDetail,
  ReceiptSyncResponse,
  ProductSalesStatsResponse,
} from '@/types/receipts'

interface ReceiptFilters {
  from_date: string
  to_date: string
  department_id?: string
  iiko_source_domain?: string
  waiter_name?: string
  min_sum?: number
  limit?: number
  offset?: number
}

export function useReceipts(filters: ReceiptFilters) {
  return useQuery<Receipt[]>({
    queryKey: ['receipts', filters],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('from_date', filters.from_date)
      params.set('to_date', filters.to_date)
      if (filters.department_id) params.set('department_id', filters.department_id)
      if (filters.iiko_source_domain) params.set('iiko_source_domain', filters.iiko_source_domain)
      if (filters.waiter_name) params.set('waiter_name', filters.waiter_name)
      if (filters.min_sum != null) params.set('min_sum', String(filters.min_sum))
      params.set('limit', String(filters.limit ?? 100))
      params.set('offset', String(filters.offset ?? 0))
      return api.get<Receipt[]>(`/api/receipts?${params}`)
    },
    enabled: !!filters.from_date && !!filters.to_date,
  })
}

export function useReceiptDetail(receiptId: number | null, openDate: string | null) {
  return useQuery<ReceiptDetail>({
    queryKey: ['receipt-detail', receiptId, openDate],
    queryFn: () =>
      api.get<ReceiptDetail>(`/api/receipts/${receiptId}?open_date=${openDate}`),
    enabled: receiptId != null && !!openDate,
  })
}

export function useProductSalesStats(params: {
  from_date: string
  to_date: string
  department_id?: string
  iiko_source_domain?: string
  limit?: number
}) {
  return useQuery<ProductSalesStatsResponse>({
    queryKey: ['product-sales-stats', params],
    queryFn: () => {
      const qs = new URLSearchParams()
      qs.set('from_date', params.from_date)
      qs.set('to_date', params.to_date)
      if (params.department_id) qs.set('department_id', params.department_id)
      if (params.iiko_source_domain) qs.set('iiko_source_domain', params.iiko_source_domain)
      if (params.limit) qs.set('limit', String(params.limit))
      return api.get<ProductSalesStatsResponse>(`/api/receipts/stats/by-product?${qs}`)
    },
    enabled: !!params.from_date && !!params.to_date,
  })
}

export function useSyncReceipts() {
  const qc = useQueryClient()
  return useMutation<ReceiptSyncResponse, Error, { from_date: string; to_date: string; department_id?: string }>({
    mutationFn: (vars) => {
      const qs = new URLSearchParams()
      qs.set('from_date', vars.from_date)
      qs.set('to_date', vars.to_date)
      if (vars.department_id) qs.set('department_id', vars.department_id)
      return api.post<ReceiptSyncResponse>(`/api/receipts/sync?${qs}`)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['receipts'] })
      void qc.invalidateQueries({ queryKey: ['product-sales-stats'] })
    },
  })
}
