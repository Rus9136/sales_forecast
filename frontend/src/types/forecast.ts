export interface BatchForecast {
  date: string
  department_id: string
  department_name: string
  predicted_sales: number | null
}

export interface ForecastComparison {
  date: string
  department_id: string
  department_name: string
  predicted_sales: number | null
  actual_sales: number
  error: number | null
  error_percentage: number | null
}

export interface ModelInfo {
  status: string
  model_type?: string
  n_features?: number
  model_path?: string
  training_metrics?: Record<string, number>
}
