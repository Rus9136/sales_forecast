export type MenuRole =
  | 'premium_anchor'
  | 'margin_driver'
  | 'traffic_driver'
  | 'image_rare'
  | 'tail'

export type ElasticityGrade = 'A' | 'B' | 'C' | 'D'

export type RecommendationStatus = 'new' | 'approved' | 'rejected' | 'applied' | 'expired'

export interface DepartmentWeekly {
  department_id: string
  department_name: string | null
  week_start: string
  total_revenue: number
  total_cost: number
  gross_profit: number
  gp_margin: number | null
  total_receipts: number
  avg_receipt_sum: number | null
  unique_guests: number
  cost_coverage: number | null
}

export interface DepartmentWeeklyResponse {
  items: DepartmentWeekly[]
  total: number
}

export interface RecommendationSummary {
  by_status: Partial<Record<RecommendationStatus, number>>
  total: number
  total_delta_gp_new: number | null
}

export interface PriceRecommendation {
  id: number
  product_id: number
  product_name: string | null
  department_id: string
  department_name: string | null
  batch_id: string
  current_price: number
  recommended_price: number
  delta_pct: number | null
  cogs: number | null
  current_qty_forecast: number | null
  new_qty_forecast: number | null
  current_gp: number | null
  expected_gp: number | null
  delta_gp: number | null
  elasticity_used: number | null
  elasticity_grade: ElasticityGrade | null
  menu_role: MenuRole | string | null
  constraints_applied: string[] | null
  llm_explanation?: string | null
  rec_type: 'optimizer' | 'experiment'
  status: RecommendationStatus
  created_at: string
  reviewed_at?: string | null
  reviewed_by: string | null
  review_comment?: string | null
}

export interface PriceRecommendationResponse {
  items: PriceRecommendation[]
  total: number
}

export interface SkuElasticity {
  product_id: number
  department_id: string
  product_name: string | null
  elasticity_mean: number
  elasticity_ci_lower: number
  elasticity_ci_upper: number
  n_price_events: number
  estimation_level: string
  reliability_grade: ElasticityGrade | string
  group_key: string | null
  diagnostics?: Record<string, unknown> | null
}

export interface SkuMenuRoleItem {
  product_id: number
  product_name: string | null
  department_id: string
  department_name: string | null
  auto_role: MenuRole | string
  manual_role: MenuRole | string | null
  effective_role: MenuRole | string
  features: Record<string, unknown> | null
  cluster_meta: Record<string, unknown> | null
}

export interface PricingRule {
  id: number
  rule_type: string
  scope_type: string
  scope_id: string | null
  params: Record<string, unknown>
  is_active: boolean
  configured_by_role: string | null
  effective_from: string
  effective_to: string | null
}

// ── C3: Экран позиции ──────────────────────────────────────────────

export interface PriceHistoryItem {
  id: number
  product_id: number
  product_name: string | null
  department_id: string
  price: number
  prev_price: number | null
  change_pct: number | null
  first_seen_date: string
  last_seen_date: string
}

export interface PriceHistoryResponse {
  items: PriceHistoryItem[]
  total: number
}

export interface SkuWeeklyItem {
  product_id: number
  product_name: string | null
  department_id: string
  department_name: string | null
  week_start: string
  total_qty: number
  total_revenue: number
  total_cost: number
  gross_profit: number
  gp_margin: number | null
  avg_price: number | null
  avg_daily_qty: number | null
  unique_receipts: number
  days_with_sales: number
  qty_cv: number | null
  cost_coverage: number | null
}

export interface SkuWeeklyResponse {
  items: SkuWeeklyItem[]
  total: number
}

/** GET /elasticity/{product_id}/{department_id} — точечная оценка с диагностикой. */
export interface SkuElasticityDetail {
  product_id: number
  department_id: string
  product_name: string | null
  elasticity_mean: number
  elasticity_ci_lower: number
  elasticity_ci_upper: number
  n_price_events: number
  estimation_level: string
  reliability_grade: ElasticityGrade | string
  group_key: string | null
  diagnostics: Record<string, unknown> | null
}

export interface PriceOutcome {
  id: number
  recommendation_id: number
  product_id: number
  product_name: string | null
  department_id: string
  department_name: string | null
  applied_at: string
  eval_window_days: number | null
  old_price: number
  new_price: number
  qty_before: number | null
  qty_after: number | null
  /** Выручка за окно замера: до изменения цены и после. */
  revenue_before: number | null
  revenue_after: number | null
  gp_before: number | null
  gp_after: number | null
  expected_delta_gp: number | null
  actual_delta_gp: number | null
  qty_change_pct: number | null
  control_qty_change_pct: number | null
  adj_qty_change_pct: number | null
  realized_elasticity: number | null
  n_control_skus: number | null
  days_before: number | null
  days_after: number | null
  counterfactual_qty: number | null
  /** Эффект решения о цене: факт минус контрфакт по тем же товарам в других точках. */
  incremental_delta_gp: number | null
  significance_z: number | null
  /** cross_store — контроль собран; none — не собран. */
  control_method: string | null
  /** false — прошли не все ворота качества, эффект не оценивался. */
  measurable: boolean | null
  not_measurable_reason: string | null
  n_control_stores: number | null
  control_qty_before: number | null
  control_qty_after: number | null
  control_trend: number | null
  /** Дней окна выброшено из-за отсутствия товара. null — снимков остатков нет. */
  days_no_stock_before: number | null
  days_no_stock_after: number | null
  store_trend_adj: number | null
  effect_ci_low: number | null
  effect_ci_high: number | null
  p_negative: number | null
  concept: string | null
}

/** День ряда «факт против контрфакта». counterfactual заполнен только после изменения цены. */
export interface OutcomeDay {
  date: string
  phase: 'before' | 'after'
  qty: number
  counterfactual: number | null
}

export interface OutcomeDailyResponse {
  outcome_id: number
  product_id: number
  product_name: string | null
  department_id: string
  department_name: string | null
  applied_at: string
  old_price: number | null
  new_price: number | null
  measurable: boolean | null
  not_measurable_reason: string | null
  counterfactual_qty: number | null
  qty_after: number | null
  incremental_delta_gp: number | null
  days: OutcomeDay[]
}

/** Эффект приказа целиком — интервал считается совместно по всем позициям. */
export interface PriceOutcomeBatch {
  id: number
  department_id: string
  department_name: string | null
  applied_at: string
  concept: string | null
  eval_window_days: number
  n_positions: number
  n_measurable: number
  gp_before: number | null
  gp_after: number | null
  actual_delta_gp: number | null
  expected_delta_gp: number | null
  effect_gp: number | null
  effect_ci_low: number | null
  effect_ci_high: number | null
  p_negative: number | null
}

export interface PriceOutcomeResponse {
  items: PriceOutcome[]
  total: number
}

export interface OutcomeSummary {
  total_evaluated: number
  expected_delta_gp: number
  actual_delta_gp: number
  positive_outcomes: number
  hit_rate: number | null
  avg_realized_elasticity: number | null
  incremental_delta_gp: number
  significant_outcomes: number
  significant_delta_gp: number
  not_measurable: number
  batches: number
  batch_effect_gp: number
  batch_ci_low: number
  batch_ci_high: number
  /** Разложение итога — только по измеримым позициям, иначе числа не сходятся. */
  decomp_positions: number
  decomp_gp_before: number
  decomp_gp_after: number
  decomp_cash: number
}

export interface BaselineItem {
  id: number
  label: string
  scope: string
  department_id: string | null
  department_name: string | null
  baseline_from: string
  baseline_to: string
  weeks: number
  total_revenue: number | null
  total_cost: number | null
  gross_profit: number | null
  gp_margin: number | null
  total_receipts: number | null
  avg_receipt_sum: number | null
  weekly_gp_avg: number | null
  weekly_gp_stddev: number | null
  active_skus: number | null
  cost_coverage: number | null
  created_at: string
}

export interface BaselineResponse {
  items: BaselineItem[]
  total: number
}

// ── Аналитика: эластичность / роли меню / аудит ────────────────────

export interface SkuElasticityRow {
  product_id: number
  department_id: string
  product_name: string | null
  elasticity_mean: number
  elasticity_ci_lower: number
  elasticity_ci_upper: number
  elasticity_se: number | null
  n_price_events: number
  n_observations: number | null
  estimation_level: string
  reliability_grade: ElasticityGrade | string
  group_key: string | null
  model_r_squared: number | null
  model_version: string | null
  updated_at: string
}

export interface SkuElasticityListResponse {
  items: SkuElasticityRow[]
  total: number
}

export interface ElasticitySummary {
  by_grade: Record<string, number>
  by_level: Record<string, number>
  total: number
  global_prior: number | null
}

export interface MenuRolesResponse {
  items: SkuMenuRoleItem[]
  total: number
}

export interface MenuRoleSummary {
  distribution: Record<string, number>
  total: number
}

export interface AuditLogItem {
  id: number
  entity_type: string
  entity_id: string | null
  action: string
  actor: string | null
  department_id: string | null
  details: Record<string, unknown> | null
  created_at: string
  /** Обогащение бэкенда: объект записи (рекомендация/роль меню) → карточка позиции. */
  object_label?: string
  object_product_id?: number
  object_department_id?: string
}

/** GET /rules/constraint-stats — сколько новых рекомендаций сдерживает каждое правило. */
export interface RuleConstraintStats {
  by_constraint: Record<string, number>
  total_new: number
}

export interface AuditLogResponse {
  items: AuditLogItem[]
  total: number
}

// ── C4: Отчёты по ценам ────────────────────────────────────────────

export type ReportType = 'weekly' | 'monthly' | 'effect'

export interface PricingReportKpis {
  // недельный / месячный отчёт
  gross_profit?: number | null
  gp_delta_pct?: number | null
  gp_margin?: number | null
  avg_receipt_sum?: number | null
  recs_approved?: number
  recs_applied?: number
  outcomes_evaluated?: number
  actual_delta_gp?: number | null
  hit_rate?: number | null
  // отчёт об эффекте решений: свой набор
  positions?: number
  cash?: number | null
  effect?: number | null
  expected?: number | null
  confirmed?: number
  /** Планка шума по «пустым» периодам: эффект меньше неё неотличим от совпадения. */
  noise_floor?: number | null
}

export interface PricingReportListItem {
  id: number
  report_type: ReportType
  scope: string
  department_id: string | null
  department_name: string | null
  period_start: string
  period_end: string
  kpis: PricingReportKpis | null
  provider: string
  model: string | null
  status: string
  created_at: string
}

export interface PricingReportDetail extends PricingReportListItem {
  data: Record<string, unknown>
  narrative: string | null
}

export interface PricingReportListResponse {
  items: PricingReportListItem[]
  total: number
}

// ── Приказы: выгрузка утверждённых цен в iiko ──────────────────────

/** draft — собран; sending — POST ушёл, ответ не получен; sent — документ создан. */
export type PriceOrderStatus = 'draft' | 'sending' | 'sent' | 'failed' | 'cancelled'

/** Статус документа на стороне iiko (NEW = черновик, PROCESSED = проведён). */
export type IikoDocumentStatus = 'NEW' | 'PROCESSED' | 'DELETED'

export interface PriceOrderPreviewItem {
  recommendation_id: number
  product_id: number
  product_code: string | null
  product_name: string | null
  menu_role: string | null
  rec_type: string | null
  old_price: number | null
  new_price: number | null
  delta_pct: number | null
  delta_gp: number | null
  iiko_product_id?: string
  catalog_document_id?: string | null
  /** Заполнено только в excluded: почему позиция не идёт в приказ. */
  reason?: string
}

export interface PriceOrderPreview {
  department_id: string
  department_name: string
  iiko_source_domain: string
  effective_date: string
  iiko_order_status: IikoDocumentStatus
  items: PriceOrderPreviewItem[]
  excluded: PriceOrderPreviewItem[]
  n_items: number
  n_excluded: number
  total_delta_gp: number
  existing_order: { id: number; status: PriceOrderStatus; iiko_document_number: string | null } | null
}

export interface PriceOrderSendResult {
  status: string
  order_id: number
  iiko_document_id: string | null
  iiko_document_number: string | null
  iiko_status: IikoDocumentStatus | null
  n_items: number
  n_excluded: number
  excluded: PriceOrderPreviewItem[]
  total_delta_gp: number
  effective_date: string
}

export interface PriceOrderListItem {
  id: number
  department_id: string
  department_name: string
  effective_date: string
  status: PriceOrderStatus
  iiko_status: IikoDocumentStatus | null
  iiko_document_id: string | null
  iiko_document_number: string | null
  n_items: number
  n_applied: number
  total_delta_gp: number | null
  error_message: string | null
  created_at: string
  sent_at: string | null
  cancelled_at: string | null
  reverses_order_id: number | null
}

export interface PriceOrderItem {
  id: number
  recommendation_id: number | null
  product_id: number
  product_name: string | null
  product_code: string | null
  old_price: number | null
  new_price: number | null
  recommendation_status: RecommendationStatus | null
  delta_gp: number | null
  applied_at: string | null
}

export interface PriceOrderDetail extends PriceOrderListItem {
  iiko_source_domain: string
  items: PriceOrderItem[]
}

export interface PriceOrderListResponse {
  items: PriceOrderListItem[]
}
