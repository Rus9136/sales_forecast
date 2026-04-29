export type CalculationModel =
  | 'flat_by_kpi'
  | 'revenue_percent_by_kpi'
  | 'revenue_direct'
  | 'combined_products'
  | 'team_revenue_by_kpi'

export interface BonusCompany {
  id: number
  code: string
  name: string
  bin: string | null
  is_active: boolean
}

export interface BonusPosition {
  id: number
  code: string
  name: string
  category: string
  iiko_role_code: string | null
  iiko_role_name: string | null
  description: string | null
  is_active: boolean
}

export interface BonusKpiDefinition {
  id: number
  code: string
  name: string
  description: string | null
  data_source_code: string
  direction: 'higher_is_better' | 'lower_is_better' | 'binary'
  default_target: string | null
  target_metric: string | null
  cap_at_100_percent: boolean
}

export interface BonusScheme {
  id: number
  department_id: string
  position_id: number | null
  team_id: number | null
  calculation_model: CalculationModel
  version: number
  effective_from: string | null
  effective_to: string | null
  config: Record<string, unknown>
  notes: string | null
  created_at: string | null
}

export interface BonusTeam {
  id: number
  department_id: string
  code: string
  name: string
  is_active: boolean
}

export interface BonusTeamPosition {
  id: number
  team_id: number
  position_id: number
  slot: string
  display_name: string | null
  distribution_weight: string
  sort_order: number
  effective_from: string | null
  effective_to: string | null
}

export interface BonusTeamDetail extends BonusTeam {
  positions: BonusTeamPosition[]
}

export interface BonusManualKpi {
  id: number
  department_id: string
  kpi_code: string
  period_year: number
  period_month: number
  fact_value: string
  notes: string | null
  document_ref: string | null
  entered_at: string | null
  entered_by: string | null
}

export interface BonusManualKpiUpsert {
  department_id: string
  kpi_code: string
  period_year: number
  period_month: number
  fact_value: string
  notes?: string | null
  document_ref?: string | null
}

export interface BonusMonthlyPlan {
  id: number
  department_id: string
  metric: string
  year: number
  month: number
  target_value: string
  notes: string | null
}

export interface BonusMonthlyPlanUpsert {
  department_id: string
  metric: string
  year: number
  month: number
  target_value: string
  notes?: string | null
}

export interface BonusCalculation {
  id: number
  employee_id: string
  department_id: string
  period_year: number
  period_month: number
  scheme_id: number
  scheme_version: number
  team_id: number | null
  team_position_slot: string | null
  overall_kpi_percent: string | null
  applied_grade_from: string | null
  applied_grade_to: string | null
  applied_coefficient: string | null
  coefficient_type: string | null
  revenue_used: string | null
  revenue_source_used: string | null
  shifts_worked: string | null
  shifts_norm: string | null
  shifts_proration_applied: boolean
  base_bonus: string
  penalties_amount: string
  final_bonus: string
  status: string
  calculated_at: string | null
  approved_at: string | null
  paid_at: string | null
  notes: string | null
}

export interface BonusCalculationDetail extends BonusCalculation {
  scheme_config_snapshot: Record<string, unknown>
  kpi_values: unknown
  breakdown: { steps: Array<Record<string, unknown>> }
  penalties: Array<{
    id: number
    reason_code: string
    reason_text: string
    penalty_percent: string | null
    penalty_amount: string
    document_ref: string | null
    applied_at: string | null
    applied_by: string | null
  }>
}

export interface BonusRunRequest {
  department_id: string
  year: number
  month: number
  scope: string  // 'all' | 'employee:<uuid>' | 'position:<code>'
}

export interface BonusRunResponse {
  requested: number
  calculated: number
  errors: Array<{ employee_id: string; error: string }>
  ids: number[]
}
