export interface SkuForecastItem {
  product_id: number
  product_name: string
  product_type: string
  group_name: string | null
  category_name: string | null
  predicted_qty: number
  avg_price: number | null
  estimated_revenue: number | null
}

export interface SkuDailyForecast {
  department_id: string
  department_name: string
  forecast_date: string
  items: SkuForecastItem[]
  total_predicted_qty: number
  total_estimated_revenue: number | null
  model_version: string | null
}

export interface SkuForecastRange {
  department_id: string
  department_name: string
  from_date: string
  to_date: string
  daily_forecasts: SkuDailyForecast[]
}

export interface SkuTopNItem {
  product_id: number
  product_name: string
  product_type: string
  group_name: string | null
  total_revenue: number
  total_qty: number
  avg_daily_qty: number
  rank: number
}

export interface SkuTopNResponse {
  department_id: string | null
  period_days: number
  items: SkuTopNItem[]
}

export interface SkuModelInfo {
  status: string
  model_path: string
  n_features: number
  training_metrics: Record<string, number> | null
  trained_at: string | null
  target_transform: string | null
}

export interface SkuRetrainResponse {
  status: string
  message: string
  metrics: Record<string, unknown>
  timestamp: string
  training_samples: number
  n_features: number
  n_unique_skus: number
  n_unique_departments: number
}
