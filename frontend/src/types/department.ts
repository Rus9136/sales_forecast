export type SegmentType =
  | 'coffeehouse'
  | 'restaurant'
  | 'confectionery'
  | 'food_court'
  | 'store'
  | 'fast_food'
  | 'bakery'
  | 'cafe'
  | 'bar'

export interface Department {
  id: string
  parent_id: string | null
  code: string | null
  code_tco: string | null
  name: string
  type: string
  taxpayer_id_number: string | null
  segment_type: SegmentType | null
  season_start_date: string | null
  season_end_date: string | null
  created_at: string
  updated_at: string
  synced_at: string
}

export interface DepartmentCreate {
  name: string
  code?: string
  code_tco?: string
  type?: string
  taxpayer_id_number?: string
  parent_id?: string
  segment_type?: SegmentType
  season_start_date?: string | null
  season_end_date?: string | null
}

export type DepartmentUpdate = Partial<DepartmentCreate>
