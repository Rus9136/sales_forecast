export interface SalesSummary {
  id: number
  department_id: string
  date: string
  total_sales: number
  created_at: string
  updated_at: string
  synced_at: string
}

export interface SalesByHour {
  id: number
  department_id: string
  date: string
  hour: number
  sales_amount: number
  created_at: string
  updated_at: string
  synced_at: string
}

export interface SyncResult {
  status: 'success' | 'error'
  message: string
  from_date: string
  to_date: string
  summary_records?: number
  hourly_records?: number
  total_raw_records?: number
  details?: string
  error_type?: string
}
