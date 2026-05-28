import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  DepartmentWeeklyResponse,
  PriceRecommendationResponse,
  RecommendationSummary,
} from '@/types/pricing'

interface DepartmentWeeklyParams {
  department_id?: string
  from_week?: string
  to_week?: string
}

export function useDepartmentWeekly(params: DepartmentWeeklyParams) {
  return useQuery<DepartmentWeeklyResponse>({
    queryKey: ['pricing', 'department-weekly', params],
    queryFn: () =>
      api.get<DepartmentWeeklyResponse>('/api/pricing-analytics/department-weekly', {
        department_id: params.department_id,
        from_week: params.from_week,
        to_week: params.to_week,
      }),
  })
}

export function useRecommendationsSummary(departmentId?: string) {
  return useQuery<RecommendationSummary>({
    queryKey: ['pricing', 'recommendations-summary', departmentId],
    queryFn: () =>
      api.get<RecommendationSummary>('/api/pricing-engine/recommendations/summary', {
        department_id: departmentId,
      }),
  })
}

interface RecommendationFilters {
  department_id?: string
  status?: string
  batch_id?: string
  limit?: number
  offset?: number
}

export function useRecommendations(filters: RecommendationFilters) {
  return useQuery<PriceRecommendationResponse>({
    queryKey: ['pricing', 'recommendations', filters],
    queryFn: () =>
      api.get<PriceRecommendationResponse>('/api/pricing-engine/recommendations', {
        department_id: filters.department_id,
        status: filters.status,
        batch_id: filters.batch_id,
        limit: String(filters.limit ?? 500),
        offset: String(filters.offset ?? 0),
      }),
  })
}

function invalidateRecommendations(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['pricing', 'recommendations'] })
  void qc.invalidateQueries({ queryKey: ['pricing', 'recommendations-summary'] })
}

export function useReviewRecommendation() {
  const qc = useQueryClient()
  return useMutation<
    unknown,
    Error,
    { id: number; status: 'approved' | 'rejected'; comment?: string; reviewerId?: string }
  >({
    mutationFn: ({ id, status, comment, reviewerId }) =>
      api.put(
        `/api/pricing-engine/recommendations/${id}/review?` +
          new URLSearchParams({
            status,
            ...(comment ? { comment } : {}),
            ...(reviewerId ? { reviewer_id: reviewerId } : {}),
          }).toString(),
        {},
      ),
    onSuccess: () => invalidateRecommendations(qc),
  })
}

export function useBatchReview() {
  const qc = useQueryClient()
  return useMutation<
    unknown,
    Error,
    { ids: number[]; status: 'approved' | 'rejected'; reviewerId?: string }
  >({
    mutationFn: ({ ids, status, reviewerId }) =>
      api.post('/api/pricing-engine/recommendations/batch-review', undefined, {
        rec_ids: ids.join(','),
        status,
        reviewer_id: reviewerId,
      }),
    onSuccess: () => invalidateRecommendations(qc),
  })
}

export function useGenerateRecommendations() {
  const qc = useQueryClient()
  return useMutation<
    { recommendations_created: number; skus_processed: number; status: string },
    Error,
    { departmentId: string; minGpThreshold?: number }
  >({
    mutationFn: ({ departmentId, minGpThreshold }) =>
      api.post('/api/pricing-engine/recommendations/generate', undefined, {
        department_id: departmentId,
        min_gp_threshold: minGpThreshold != null ? String(minGpThreshold) : undefined,
      }),
    onSuccess: () => invalidateRecommendations(qc),
  })
}
