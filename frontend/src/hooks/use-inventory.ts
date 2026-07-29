import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  InventoryStore,
  InventorySupplier,
  SupplyLoopRow,
  WriteoffProductRow,
  WriteoffSummary,
  WriteoffTrendPoint,
} from '@/types/inventory'

interface PeriodFilters {
  department_id: string
  from_date: string
  to_date: string
}

function periodParams(f: PeriodFilters): URLSearchParams {
  const params = new URLSearchParams()
  params.set('department_id', f.department_id)
  params.set('from_date', f.from_date)
  params.set('to_date', f.to_date)
  return params
}

export function useWriteoffSummary(filters: PeriodFilters, enabled = true) {
  return useQuery<WriteoffSummary>({
    queryKey: ['inventory', 'writeoffs', 'summary', filters],
    queryFn: () =>
      api.get<WriteoffSummary>(`/api/inventory/writeoffs/summary?${periodParams(filters)}`),
    enabled: enabled && Boolean(filters.department_id),
  })
}

export function useWriteoffByProduct(
  filters: PeriodFilters & { store_id?: string; reason_id?: string; limit?: number },
  enabled = true,
) {
  return useQuery<WriteoffProductRow[]>({
    queryKey: ['inventory', 'writeoffs', 'by-product', filters],
    queryFn: () => {
      const params = periodParams(filters)
      if (filters.store_id) params.set('store_id', filters.store_id)
      if (filters.reason_id) params.set('reason_id', filters.reason_id)
      params.set('limit', String(filters.limit ?? 50))
      return api.get<WriteoffProductRow[]>(`/api/inventory/writeoffs/by-product?${params}`)
    },
    enabled: enabled && Boolean(filters.department_id),
  })
}

export function useWriteoffTrend(filters: PeriodFilters, enabled = true) {
  return useQuery<WriteoffTrendPoint[]>({
    queryKey: ['inventory', 'writeoffs', 'trend', filters],
    queryFn: () =>
      api.get<WriteoffTrendPoint[]>(`/api/inventory/writeoffs/trend?${periodParams(filters)}`),
    enabled: enabled && Boolean(filters.department_id),
  })
}

export function useSupplyLoop(
  filters: PeriodFilters & { supplier_id?: string; limit?: number },
  enabled = true,
) {
  return useQuery<SupplyLoopRow[]>({
    queryKey: ['inventory', 'supply-loop', filters],
    queryFn: () => {
      const params = periodParams(filters)
      if (filters.supplier_id) params.set('supplier_id', filters.supplier_id)
      params.set('limit', String(filters.limit ?? 200))
      return api.get<SupplyLoopRow[]>(`/api/inventory/supply-loop?${params}`)
    },
    enabled: enabled && Boolean(filters.department_id),
  })
}

export function useInventorySuppliers(filters: PeriodFilters, enabled = true) {
  return useQuery<InventorySupplier[]>({
    queryKey: ['inventory', 'suppliers', filters],
    queryFn: () =>
      api.get<InventorySupplier[]>(`/api/inventory/suppliers?${periodParams(filters)}`),
    enabled: enabled && Boolean(filters.department_id),
  })
}

export function useInventoryStores(departmentId?: string) {
  return useQuery<InventoryStore[]>({
    queryKey: ['inventory', 'stores', departmentId],
    queryFn: () => {
      const params = new URLSearchParams()
      if (departmentId) params.set('department_id', departmentId)
      return api.get<InventoryStore[]>(`/api/inventory/stores?${params}`)
    },
    enabled: Boolean(departmentId),
  })
}

export function useInventorySync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      from_date: string
      to_date: string
      department_id?: string
    }) => {
      const params = new URLSearchParams()
      params.set('from_date', payload.from_date)
      params.set('to_date', payload.to_date)
      if (payload.department_id) params.set('department_id', payload.department_id)
      return api.post(`/api/inventory/sync?${params}`, {})
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory'] }),
  })
}
