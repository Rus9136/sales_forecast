export type MenuRole =
  | 'premium_anchor'
  | 'margin_driver'
  | 'traffic_driver'
  | 'image_rare'
  | 'tail'

export type ElasticityGrade = 'A' | 'B' | 'C' | 'D'

export type RecommendationStatus = 'new' | 'approved' | 'rejected' | 'expired'

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
  status: RecommendationStatus
  created_at: string
  reviewed_at?: string | null
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
