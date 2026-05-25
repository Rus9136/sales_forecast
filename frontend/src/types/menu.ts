export type ProductType = 'DISH' | 'GOODS' | 'MODIFIER' | 'PREPARED' | 'SERVICE'

export interface NomenclatureCategory {
  id: number
  iiko_source_domain: string
  iiko_category_id: string
  name: string
  is_deleted: boolean
}

export interface NomenclatureGroup {
  id: number
  iiko_source_domain: string
  iiko_group_id: string
  parent_id: number | null
  name: string
  num: string | null
  code: string | null
  position: number | null
  is_deleted: boolean
}

export interface NomenclatureGroupTreeNode {
  id: number
  iiko_group_id: string
  name: string
  code: string | null
  position: number | null
  is_deleted: boolean
  children: NomenclatureGroupTreeNode[]
}

export interface Product {
  id: number
  iiko_source_domain: string
  iiko_product_id: string
  num: string | null
  code: string | null
  name: string
  description: string | null
  type: ProductType
  group_id: number | null
  category_id: number | null
  default_sale_price: string | null
  estimated_purchase_price: string | null
  weight_kg: string | null
  cold_loss_percent: string | null
  hot_loss_percent: string | null
  is_deleted: boolean
  is_included_in_menu: boolean
}

export interface ProductDetail extends Product {
  group_name: string | null
  category_name: string | null
}

export interface NomenclatureSyncResponse {
  status: string
  total_categories: number
  total_groups: number
  total_products: number
  per_domain: Array<{
    domain: string
    categories: number
    groups: number
    products: number
  }>
  errors: string[]
}

export interface ProductListFilters {
  search?: string
  iiko_source_domain?: string
  group_id?: number
  category_id?: number
  type?: ProductType
  include_deleted?: boolean
  limit?: number
  offset?: number
}
