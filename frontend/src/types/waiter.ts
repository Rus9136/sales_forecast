export interface Employee {
  id: string
  code: string | null
  name: string
  login: string | null
  first_name: string | null
  middle_name: string | null
  last_name: string | null
  main_role_code: string | null
  main_role_name: string | null
  role_codes: string[] | null
  department_codes: string[] | null
  preferred_department_code: string | null
  cell_phone: string | null
  email: string | null
  hire_date: string | null
  fire_date: string | null
  deleted: boolean
  synced_at: string
}

export interface SalesByWaiter {
  department_id: string
  date: string
  waiter_name: string
  employee_id: string | null
  total_sales: number
  total_sales_with_discount: number | null
  synced_at: string
}

export interface WaiterSyncResult {
  status: 'success' | 'error'
  message: string
  new?: number
  updated?: number
  skipped?: number
  total_raw_records?: number
  from_date?: string | null
  to_date?: string | null
  error_type?: string
}

export interface EmployeesSyncResult {
  status: 'success' | 'error'
  message: string
  new?: number
  updated?: number
  total?: number
}
