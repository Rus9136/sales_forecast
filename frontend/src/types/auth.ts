export type SectionKey =
  | 'dashboard'
  | 'departments'
  | 'employees'
  | 'sales.daily'
  | 'sales.hourly'
  | 'sales.waiters'
  | 'forecast.branches'
  | 'forecast.comparison'
  | 'forecast.sku'
  | 'menu.products'
  | 'menu.groups'
  | 'receipts.list'
  | 'receipts.stats'
  | 'ai.recommendations'
  | 'pricing.dashboard'
  | 'pricing.recommendations'
  | 'pricing.rules'
  | 'pricing.position_detail'
  | 'pricing.outcomes'
  | 'pricing.analytics'
  | 'pricing.reports'
  | 'sync'
  | 'users'
  | 'roles'

export interface AppUser {
  id: string
  phone: string
  full_name: string | null
  role_code: string
  role_name: string | null
  is_active: boolean
  allowed_sections: SectionKey[]
  created_at: string | null
  last_login_at: string | null
}

export interface AppRole {
  code: string
  name: string
  allowed_sections: SectionKey[]
  is_system: boolean
  updated_at: string | null
}

export interface LoginResponse {
  session_token: string
  expires_at: string
  user: AppUser
}

export interface RolesResponse {
  roles: AppRole[]
  available_sections: SectionKey[]
}

export interface UserCreatePayload {
  phone: string
  full_name?: string | null
  role_code: string
  is_active?: boolean
}

export interface UserUpdatePayload {
  phone?: string
  full_name?: string | null
  role_code?: string
  is_active?: boolean
}
