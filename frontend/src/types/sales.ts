export interface SalesSummary {
  id: number
  department_id: string
  date: string
  total_sales: number          // прайс (DishSumInt)
  total_paid: number | null    // к оплате (DishDiscountSumInt); null до бэкфилла
  created_at: string
  updated_at: string
  synced_at: string
}

export interface SalesByHour {
  id: number
  department_id: string
  date: string
  hour: number
  sales_amount: number         // прайс
  paid_amount: number | null   // к оплате; null до бэкфилла
  created_at: string
  updated_at: string
  synced_at: string
}

export interface SalesHeatmap {
  from_date: string | null
  to_date: string | null
  department_id: string | null
  /** 7×24 grid: rows are Mon..Sun, cols are 0..23 hours. */
  grid: number[][]
  /** 7×24 grid «к оплате» (paid). */
  grid_paid: number[][]
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
