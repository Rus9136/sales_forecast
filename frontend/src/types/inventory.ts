export interface WriteoffBreakdownRow {
  store_id: string | null
  store_name: string
  reason_id: string | null
  reason: string
  documents: number
  positions: number
  cost: number
  share_of_total: number
}

export interface WriteoffSummary {
  department_id: string
  from_date: string
  to_date: string
  total_writeoff_cost: number
  revenue: number
  supply_cost: number
  writeoff_share_of_revenue: number | null
  writeoff_share_of_supply: number | null
  revenue_basis: string
  breakdown: WriteoffBreakdownRow[]
}

export interface WriteoffProductRow {
  product_id: number
  product_name: string
  product_type: string
  unit: string | null
  written_amount: number
  written_cost: number
  documents: number
  days_with_writeoff: number
  reasons: string[]
  supplied_amount: number | null
  supplied_sum: number | null
  loss_rate: number | null
}

export interface WriteoffTrendPoint {
  week: string
  writeoff_cost: number
  revenue: number
  share_of_revenue: number | null
}

export interface SupplyLoopRow {
  product_id: number
  product_name: string
  product_type: string
  unit: string | null
  supplied_amount: number
  supplied_sum: number
  supply_days: number
  last_supply_date: string | null
  avg_purchase_price: number | null
  sold_qty: number
  sale_days: number
  revenue: number
  sold_cost: number
  written_amount: number
  written_cost: number
  loss_rate: number | null
  is_resale: boolean
}

export interface InventorySupplier {
  supplier_id: string | null
  supplier_name: string
  invoices: number
  positions: number
  total_sum: number
  is_internal: boolean
}

export interface InventoryStore {
  id: string
  name: string
  code: string | null
  department_id: string | null
  department_name: string | null
}
