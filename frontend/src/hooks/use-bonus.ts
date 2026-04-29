import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  BonusCompany,
  BonusPosition,
  BonusKpiDefinition,
  BonusScheme,
  BonusTeam,
  BonusTeamDetail,
  BonusManualKpi,
  BonusManualKpiUpsert,
  BonusMonthlyPlan,
  BonusMonthlyPlanUpsert,
  BonusCalculation,
  BonusCalculationDetail,
  BonusRunRequest,
  BonusRunResponse,
} from '@/types/bonus'

// ---------------------------------------------------------------------------
// Catalogues
// ---------------------------------------------------------------------------
export function useBonusCompanies() {
  return useQuery({
    queryKey: ['bonus', 'companies'],
    queryFn: () => api.get<BonusCompany[]>('/api/bonus/companies'),
  })
}

export function useBonusPositions() {
  return useQuery({
    queryKey: ['bonus', 'positions'],
    queryFn: () => api.get<BonusPosition[]>('/api/bonus/positions'),
  })
}

export function useBonusKpiDefinitions() {
  return useQuery({
    queryKey: ['bonus', 'kpi-definitions'],
    queryFn: () => api.get<BonusKpiDefinition[]>('/api/bonus/kpi-definitions'),
  })
}

export function useCalculationModels() {
  return useQuery({
    queryKey: ['bonus', 'calculation-models'],
    queryFn: () => api.get<string[]>('/api/bonus/config/calculation-models'),
  })
}

export function useDataSources() {
  return useQuery({
    queryKey: ['bonus', 'data-sources'],
    queryFn: () => api.get<string[]>('/api/bonus/config/data-sources'),
  })
}

// ---------------------------------------------------------------------------
// Schemes
// ---------------------------------------------------------------------------
export function useBonusSchemes(filters?: { department_id?: string; position_id?: number }) {
  return useQuery({
    queryKey: ['bonus', 'schemes', filters],
    queryFn: () =>
      api.get<BonusScheme[]>('/api/bonus/schemes', {
        department_id: filters?.department_id,
        position_id: filters?.position_id ? String(filters.position_id) : undefined,
      }),
  })
}

export function useBonusScheme(id: number | null) {
  return useQuery({
    enabled: id != null,
    queryKey: ['bonus', 'schemes', id],
    queryFn: () => api.get<BonusScheme>(`/api/bonus/schemes/${id}`),
  })
}

// ---------------------------------------------------------------------------
// Teams
// ---------------------------------------------------------------------------
export function useBonusTeams(department_id?: string) {
  return useQuery({
    queryKey: ['bonus', 'teams', department_id],
    queryFn: () =>
      api.get<BonusTeam[]>('/api/bonus/teams', { department_id }),
  })
}

export function useBonusTeam(id: number | null) {
  return useQuery({
    enabled: id != null,
    queryKey: ['bonus', 'teams', id],
    queryFn: () => api.get<BonusTeamDetail>(`/api/bonus/teams/${id}`),
  })
}

// ---------------------------------------------------------------------------
// Manual KPI
// ---------------------------------------------------------------------------
export function useManualKpi(filters: { department_id?: string; year?: number; month?: number }) {
  return useQuery({
    queryKey: ['bonus', 'manual-kpi', filters],
    queryFn: () =>
      api.get<BonusManualKpi[]>('/api/bonus/manual-kpi', {
        department_id: filters.department_id,
        year: filters.year ? String(filters.year) : undefined,
        month: filters.month ? String(filters.month) : undefined,
      }),
  })
}

export function useUpsertManualKpi() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BonusManualKpiUpsert) =>
      api.post<BonusManualKpi>('/api/bonus/manual-kpi', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'manual-kpi'] }),
  })
}

export function useDeleteManualKpi() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/api/bonus/manual-kpi/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'manual-kpi'] }),
  })
}

// ---------------------------------------------------------------------------
// Monthly plans
// ---------------------------------------------------------------------------
export function useMonthlyPlans(filters: { department_id?: string; year?: number; metric?: string }) {
  return useQuery({
    queryKey: ['bonus', 'monthly-plans', filters],
    queryFn: () =>
      api.get<BonusMonthlyPlan[]>('/api/bonus/monthly-plans', {
        department_id: filters.department_id,
        year: filters.year ? String(filters.year) : undefined,
        metric: filters.metric,
      }),
  })
}

export function useUpsertMonthlyPlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BonusMonthlyPlanUpsert) =>
      api.post<BonusMonthlyPlan>('/api/bonus/monthly-plans', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'monthly-plans'] }),
  })
}

// ---------------------------------------------------------------------------
// Calculations
// ---------------------------------------------------------------------------
export function useBonusCalculations(filters: {
  department_id?: string
  year?: number
  month?: number
  status?: string
  employee_id?: string
}) {
  return useQuery({
    queryKey: ['bonus', 'calculations', filters],
    queryFn: () =>
      api.get<BonusCalculation[]>('/api/bonus/calculations', {
        department_id: filters.department_id,
        year: filters.year ? String(filters.year) : undefined,
        month: filters.month ? String(filters.month) : undefined,
        status: filters.status,
        employee_id: filters.employee_id,
      }),
  })
}

export function useBonusCalculation(id: number | null) {
  return useQuery({
    enabled: id != null,
    queryKey: ['bonus', 'calculations', id],
    queryFn: () => api.get<BonusCalculationDetail>(`/api/bonus/calculations/${id}`),
  })
}

export function useRunBonusCalculation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BonusRunRequest) =>
      api.post<BonusRunResponse>('/api/bonus/calculations/run', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'calculations'] }),
  })
}

export function useApproveCalculation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      api.post<{ id: number; status: string }>(`/api/bonus/calculations/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'calculations'] }),
  })
}

export function useRejectCalculation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      api.post<{ id: number; status: string }>(
        `/api/bonus/calculations/${id}/reject`,
        undefined,
        { reason },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bonus', 'calculations'] }),
  })
}
