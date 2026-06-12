import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  AuditLogResponse,
  BaselineResponse,
  DepartmentWeeklyResponse,
  ElasticitySummary,
  MenuRoleSummary,
  MenuRolesResponse,
  OutcomeSummary,
  PriceHistoryResponse,
  PriceOutcomeResponse,
  PriceRecommendation,
  PriceRecommendationResponse,
  PricingReportDetail,
  PricingReportListResponse,
  PricingRule,
  RecommendationSummary,
  ReportType,
  SkuElasticityDetail,
  SkuElasticityListResponse,
  SkuMenuRoleItem,
  SkuWeeklyResponse,
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

/** C4': сгенерировать LLM-обоснование одной рекомендации (5–15 с). */
export function useExplainRecommendation() {
  const qc = useQueryClient()
  return useMutation<
    { status: string; recommendation_id: number; structured: boolean; explanation: string },
    Error,
    { id: number }
  >({
    mutationFn: ({ id }) =>
      api.post(`/api/pricing-engine/recommendations/${id}/explain`, undefined),
    onSuccess: () => invalidateRecommendations(qc),
  })
}

// ── C3: Экран позиции ──────────────────────────────────────────────

interface SkuKey {
  productId: number
  departmentId: string
}

/** История фактических ценовых событий SKU (sku_price_history). */
export function useSkuPriceHistory({ productId, departmentId, fromDate }: SkuKey & { fromDate?: string }) {
  return useQuery<PriceHistoryResponse>({
    queryKey: ['pricing', 'price-history', productId, departmentId, fromDate],
    queryFn: () =>
      api.get<PriceHistoryResponse>('/api/pricing-analytics/price-history', {
        product_id: String(productId),
        department_id: departmentId,
        from_date: fromDate,
        limit: '1000',
      }),
    enabled: Number.isFinite(productId) && !!departmentId,
  })
}

/** Недельные агрегаты SKU × подразделение (sku_weekly_summary). */
export function useSkuWeekly({ productId, departmentId, fromWeek }: SkuKey & { fromWeek?: string }) {
  return useQuery<SkuWeeklyResponse>({
    queryKey: ['pricing', 'sku-weekly', productId, departmentId, fromWeek],
    queryFn: () =>
      api.get<SkuWeeklyResponse>('/api/pricing-analytics/sku-weekly', {
        product_id: String(productId),
        department_id: departmentId,
        from_week: fromWeek,
        limit: '500',
      }),
    enabled: Number.isFinite(productId) && !!departmentId,
  })
}

/** Точечная оценка эластичности SKU с диагностикой (404 → null). */
export function useSkuElasticity({ productId, departmentId }: SkuKey) {
  return useQuery<SkuElasticityDetail | null>({
    queryKey: ['pricing', 'elasticity-detail', productId, departmentId],
    queryFn: async () => {
      try {
        return await api.get<SkuElasticityDetail>(
          `/api/pricing-engine/elasticity/${productId}/${departmentId}`,
        )
      } catch (e) {
        if ((e as { status?: number }).status === 404) return null
        throw e
      }
    },
    enabled: Number.isFinite(productId) && !!departmentId,
    retry: false,
  })
}

/** Роль позиции в меню (одна запись по паре product×dept). */
export function useSkuMenuRole({ productId, departmentId }: SkuKey) {
  return useQuery<SkuMenuRoleItem | null>({
    queryKey: ['pricing', 'menu-role', productId, departmentId],
    queryFn: async () => {
      const res = await api.get<{ items: SkuMenuRoleItem[] }>('/api/pricing-analytics/menu-roles', {
        product_id: String(productId),
        department_id: departmentId,
        limit: '1',
      })
      return res.items[0] ?? null
    },
    enabled: Number.isFinite(productId) && !!departmentId,
  })
}

/** Ручное переопределение роли меню (пустая строка снимает override). */
export function useOverrideMenuRole() {
  const qc = useQueryClient()
  return useMutation<
    { status: string; effective_role: string },
    Error,
    { productId: number; departmentId: string; manualRole: string }
  >({
    mutationFn: ({ productId, departmentId, manualRole }) =>
      api.put(
        `/api/pricing-analytics/menu-roles/${productId}/${departmentId}?` +
          new URLSearchParams({ manual_role: manualRole }).toString(),
        {},
      ),
    onSuccess: (_res, vars) => {
      void qc.invalidateQueries({ queryKey: ['pricing', 'menu-role', vars.productId, vars.departmentId] })
      void qc.invalidateQueries({ queryKey: ['pricing', 'recommendations'] })
    },
  })
}

/** Рекомендации по подразделению, отфильтрованные по конкретному SKU. */
export function useSkuRecommendations({ productId, departmentId }: SkuKey) {
  return useQuery<PriceRecommendationResponse, Error, PriceRecommendation[]>({
    queryKey: ['pricing', 'recommendations', 'by-sku', productId, departmentId],
    queryFn: () =>
      api.get<PriceRecommendationResponse>('/api/pricing-engine/recommendations', {
        department_id: departmentId,
        limit: '1000',
      }),
    enabled: Number.isFinite(productId) && !!departmentId,
    select: (res) => (res.items ?? []).filter((r) => r.product_id === productId),
  })
}

/** Измеренные результаты применённых рекомендаций по SKU (фидбек-loop). */
export function useSkuOutcomes({ productId, departmentId }: SkuKey) {
  return useQuery<PriceOutcomeResponse, Error, PriceOutcomeResponse['items']>({
    queryKey: ['pricing', 'outcomes', 'by-sku', productId, departmentId],
    queryFn: () =>
      api.get<PriceOutcomeResponse>('/api/pricing-engine/outcomes', {
        department_id: departmentId,
        limit: '500',
      }),
    enabled: Number.isFinite(productId) && !!departmentId,
    select: (res) => res.items ?? [],
  })
}

// ── B4: Бизнес-правила ─────────────────────────────────────────────

interface RulesResponse {
  items: PricingRule[]
  total: number
}

export function usePricingRules() {
  return useQuery<RulesResponse>({
    queryKey: ['pricing', 'rules'],
    queryFn: () => api.get<RulesResponse>('/api/pricing-engine/rules'),
  })
}

function invalidateRules(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['pricing', 'rules'] })
}

export function useCreatePricingRule() {
  const qc = useQueryClient()
  return useMutation<
    PricingRule,
    Error,
    { ruleType: string; scopeType: string; scopeId?: string; params: Record<string, unknown>; configuredByRole?: string }
  >({
    mutationFn: ({ ruleType, scopeType, scopeId, params, configuredByRole }) =>
      api.post<PricingRule>('/api/pricing-engine/rules', undefined, {
        rule_type: ruleType,
        scope_type: scopeType,
        scope_id: scopeId,
        params: JSON.stringify(params),
        configured_by_role: configuredByRole,
      }),
    onSuccess: () => invalidateRules(qc),
  })
}

export function useUpdatePricingRule() {
  const qc = useQueryClient()
  return useMutation<
    PricingRule,
    Error,
    { id: number; params?: Record<string, unknown>; isActive?: boolean }
  >({
    mutationFn: ({ id, params, isActive }) => {
      const q = new URLSearchParams()
      if (params !== undefined) q.set('params', JSON.stringify(params))
      if (isActive !== undefined) q.set('is_active', String(isActive))
      return api.put<PricingRule>(`/api/pricing-engine/rules/${id}?${q.toString()}`, {})
    },
    onSuccess: () => invalidateRules(qc),
  })
}

export function useDeletePricingRule() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, number>({
    mutationFn: (id) => api.delete(`/api/pricing-engine/rules/${id}`),
    onSuccess: () => invalidateRules(qc),
  })
}

// ── FB: Фидбек-loop (outcomes / baseline / эксперименты) ───────────

export function useOutcomes(departmentId?: string) {
  return useQuery<PriceOutcomeResponse>({
    queryKey: ['pricing', 'outcomes', departmentId],
    queryFn: () =>
      api.get<PriceOutcomeResponse>('/api/pricing-engine/outcomes', {
        department_id: departmentId,
        limit: '500',
      }),
  })
}

export function useOutcomesSummary(departmentId?: string) {
  return useQuery<OutcomeSummary>({
    queryKey: ['pricing', 'outcomes-summary', departmentId],
    queryFn: () =>
      api.get<OutcomeSummary>('/api/pricing-engine/outcomes/summary', {
        department_id: departmentId,
      }),
  })
}

export function useBaseline(label?: string) {
  return useQuery<BaselineResponse>({
    queryKey: ['pricing', 'baseline', label],
    queryFn: () =>
      api.get<BaselineResponse>('/api/pricing-engine/baseline', { label }),
  })
}

function invalidateOutcomes(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['pricing', 'outcomes'] })
  void qc.invalidateQueries({ queryKey: ['pricing', 'outcomes-summary'] })
}

export function useEvaluateOutcomes() {
  const qc = useQueryClient()
  return useMutation<{ status: string; pending: number; evaluated: number; skipped: number }, Error, void>({
    mutationFn: () => api.post('/api/pricing-engine/outcomes/evaluate', undefined),
    onSuccess: () => invalidateOutcomes(qc),
  })
}

export function useGenerateExperiments() {
  const qc = useQueryClient()
  return useMutation<
    { status: string; batch_id: string; candidates: number; experiments_created: number },
    Error,
    { departmentId: string; n?: number; deltaPct?: number }
  >({
    mutationFn: ({ departmentId, n, deltaPct }) =>
      api.post('/api/pricing-engine/experiments/generate', undefined, {
        department_id: departmentId,
        n: n != null ? String(n) : undefined,
        delta_pct: deltaPct != null ? String(deltaPct) : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pricing', 'recommendations'] })
    },
  })
}

// ── Аналитика: эластичность (B2) ───────────────────────────────────

interface ElasticityFilters {
  department_id?: string
  reliability_grade?: string
  estimation_level?: string
  limit?: number
  offset?: number
}

export function useElasticityList(filters: ElasticityFilters) {
  return useQuery<SkuElasticityListResponse>({
    queryKey: ['pricing', 'elasticity-list', filters],
    queryFn: () =>
      api.get<SkuElasticityListResponse>('/api/pricing-engine/elasticity', {
        department_id: filters.department_id,
        reliability_grade: filters.reliability_grade,
        estimation_level: filters.estimation_level,
        limit: String(filters.limit ?? 200),
        offset: String(filters.offset ?? 0),
      }),
  })
}

export function useElasticitySummary() {
  return useQuery<ElasticitySummary>({
    queryKey: ['pricing', 'elasticity-summary'],
    queryFn: () => api.get<ElasticitySummary>('/api/pricing-engine/elasticity/summary'),
  })
}

// ── Аналитика: роли меню (B1) ──────────────────────────────────────

interface MenuRolesFilters {
  department_id?: string
  effective_role?: string
  limit?: number
  offset?: number
}

export function useMenuRolesList(filters: MenuRolesFilters) {
  return useQuery<MenuRolesResponse>({
    queryKey: ['pricing', 'menu-roles-list', filters],
    queryFn: () =>
      api.get<MenuRolesResponse>('/api/pricing-analytics/menu-roles', {
        department_id: filters.department_id,
        effective_role: filters.effective_role,
        limit: String(filters.limit ?? 200),
        offset: String(filters.offset ?? 0),
      }),
  })
}

export function useMenuRolesSummary(departmentId?: string) {
  return useQuery<MenuRoleSummary>({
    queryKey: ['pricing', 'menu-roles-summary', departmentId],
    queryFn: () =>
      api.get<MenuRoleSummary>('/api/pricing-analytics/menu-roles/summary', {
        department_id: departmentId,
      }),
  })
}

export function useClusterMenuRoles() {
  const qc = useQueryClient()
  return useMutation<
    { status: string; skus_classified: number; silhouette_score: number; lookback_days: number },
    Error,
    { lookbackDays?: number }
  >({
    mutationFn: ({ lookbackDays }) =>
      api.post('/api/pricing-analytics/menu-roles/cluster', undefined, {
        lookback_days: lookbackDays != null ? String(lookbackDays) : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pricing', 'menu-roles-list'] })
      void qc.invalidateQueries({ queryKey: ['pricing', 'menu-roles-summary'] })
    },
  })
}

// ── Аналитика: аудит (AU) ──────────────────────────────────────────

interface AuditFilters {
  entity_type?: string
  action?: string
  department_id?: string
  limit?: number
  offset?: number
}

export function useAuditLog(filters: AuditFilters) {
  return useQuery<AuditLogResponse>({
    queryKey: ['pricing', 'audit-log', filters],
    queryFn: () =>
      api.get<AuditLogResponse>('/api/pricing-engine/audit-log', {
        entity_type: filters.entity_type,
        action: filters.action,
        department_id: filters.department_id,
        limit: String(filters.limit ?? 100),
        offset: String(filters.offset ?? 0),
      }),
  })
}

// ── C4: Отчёты по ценам ────────────────────────────────────────────

export function usePricingReports(filters: { report_type?: string; department_id?: string }) {
  return useQuery<PricingReportListResponse>({
    queryKey: ['pricing', 'reports', filters],
    queryFn: () =>
      api.get<PricingReportListResponse>('/api/pricing-engine/reports', {
        report_type: filters.report_type,
        department_id: filters.department_id,
        limit: '100',
      }),
  })
}

export function usePricingReport(id: number | null) {
  return useQuery<PricingReportDetail>({
    queryKey: ['pricing', 'report', id],
    queryFn: () => api.get<PricingReportDetail>(`/api/pricing-engine/reports/${id}`),
    enabled: id != null,
  })
}

export function useGeneratePricingReport() {
  const qc = useQueryClient()
  return useMutation<
    { id: number; status: string; has_narrative: boolean; period_start: string; period_end: string },
    Error,
    { reportType: ReportType; departmentId?: string }
  >({
    mutationFn: ({ reportType, departmentId }) =>
      api.post('/api/pricing-engine/reports/generate', undefined, {
        report_type: reportType,
        department_id: departmentId,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pricing', 'reports'] })
    },
  })
}
