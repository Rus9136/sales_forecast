export interface ReceiptItem {
  id: number
  product_id: number | null
  iiko_dish_id: string | null
  dish_name: string
  dish_code: string | null
  dish_group: string | null
  dish_category: string | null
  qty: number
  price_per_unit: number | null
  dish_sum: number        // сумма по прайсу (DishSumInt)
  paid_sum: number        // сумма к оплате со скидкой/сервисом (DishDiscountSumInt)
  discount: number        // dish_sum - paid_sum (>0 скидка, <0 наценка/сервис)
  return_sum: number
  cost_price: number | null
  food_cost_percent: number | null
  margin: number | null
}

export interface Receipt {
  id: number
  department_id: string
  department_name: string | null
  open_date: string
  order_num: number
  close_time: string
  order_type: string | null
  table_num: string | null
  waiter_name: string | null
  guest_num: number | null
  total_sum: number       // сумма по прайсу (DishSumInt)
  paid_sum: number        // сумма к оплате со скидкой/сервисом (DishDiscountSumInt)
  discount: number        // total_sum - paid_sum (>0 скидка, <0 наценка/сервис)
  return_sum: number
  items_count: number
  synced_at: string
}

export interface ReceiptDetail extends Receipt {
  items: ReceiptItem[]
}

export interface ReceiptSyncResponse {
  status: string
  total_receipts: number
  total_items: number
  per_domain: Array<{ domain: string; receipts: number; items: number }>
  errors: string[]
}

export interface ProductSalesStats {
  product_id: number | null
  iiko_dish_id: string | null
  dish_name: string
  dish_group: string | null
  dish_category: string | null
  total_qty: number
  total_sum: number
  total_discount: number
  total_cost: number | null
  receipts_count: number
  avg_price: number | null
  avg_cost: number | null
  avg_food_cost_pct: number | null
  margin: number | null
}

export interface ProductSalesStatsResponse {
  period_start: string
  period_end: string
  department_id: string | null
  items: ProductSalesStats[]
  total_revenue: number
  total_cost: number
  total_margin: number
  total_items_sold: number
}
