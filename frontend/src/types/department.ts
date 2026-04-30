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

export type LocationType =
  | 'city_center'
  | 'mall'
  | 'business_district'
  | 'resort_mountain'
  | 'resort_lake'
  | 'visit_center'
  | 'other'

export type SeasonalityIntensity = 'none' | 'low' | 'medium' | 'high'

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
  brand: string | null
  location_type: LocationType | null
  tourist_traffic_dependent: boolean
  is_24_7: boolean
  opening_hour: number | null
  closing_hour: number | null
  seasonality_intensity: SeasonalityIntensity
  city: string | null
  opened_date: string | null
  season_start_month: number | null
  season_end_month: number | null
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
  brand?: string | null
  location_type?: LocationType | null
  tourist_traffic_dependent?: boolean
  is_24_7?: boolean
  opening_hour?: number | null
  closing_hour?: number | null
  seasonality_intensity?: SeasonalityIntensity
  city?: string | null
  opened_date?: string | null
  season_start_month?: number | null
  season_end_month?: number | null
}

export type DepartmentUpdate = Partial<DepartmentCreate>
