import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  NomenclatureCategory,
  NomenclatureGroup,
  NomenclatureGroupTreeNode,
  NomenclatureSyncResponse,
  Product,
  ProductDetail,
  ProductListFilters,
  RecipeDetail,
  RecipeSyncResponse,
} from '@/types/menu'

function toParams(filters: ProductListFilters): Record<string, string> {
  const out: Record<string, string> = {}
  if (filters.search) out.search = filters.search
  if (filters.iiko_source_domain) out.iiko_source_domain = filters.iiko_source_domain
  if (filters.group_id != null) out.group_id = String(filters.group_id)
  if (filters.category_id != null) out.category_id = String(filters.category_id)
  if (filters.type) out.type = filters.type
  if (filters.include_deleted) out.include_deleted = 'true'
  if (filters.limit != null) out.limit = String(filters.limit)
  if (filters.offset != null) out.offset = String(filters.offset)
  return out
}

export function useProducts(filters: ProductListFilters = {}) {
  return useQuery({
    queryKey: ['menu', 'products', filters],
    queryFn: () => api.get<Product[]>('/api/menu/products', toParams(filters)),
  })
}

export function useProduct(id: number | null) {
  return useQuery({
    queryKey: ['menu', 'product', id],
    queryFn: () => api.get<ProductDetail>(`/api/menu/products/${id}`),
    enabled: id != null,
  })
}

export function useNomenclatureGroups(iikoSourceDomain?: string) {
  return useQuery({
    queryKey: ['menu', 'groups', iikoSourceDomain ?? '__all__'],
    queryFn: () =>
      api.get<NomenclatureGroup[]>(
        '/api/menu/groups',
        iikoSourceDomain ? { iiko_source_domain: iikoSourceDomain } : undefined,
      ),
  })
}

export function useNomenclatureGroupsTree(iikoSourceDomain?: string) {
  return useQuery({
    queryKey: ['menu', 'groups-tree', iikoSourceDomain ?? '__all__'],
    queryFn: () =>
      api.get<NomenclatureGroupTreeNode[]>(
        '/api/menu/groups/tree',
        iikoSourceDomain ? { iiko_source_domain: iikoSourceDomain } : undefined,
      ),
  })
}

export function useNomenclatureCategories(iikoSourceDomain?: string) {
  return useQuery({
    queryKey: ['menu', 'categories', iikoSourceDomain ?? '__all__'],
    queryFn: () =>
      api.get<NomenclatureCategory[]>(
        '/api/menu/categories',
        iikoSourceDomain ? { iiko_source_domain: iikoSourceDomain } : undefined,
      ),
  })
}

export function useSyncNomenclature() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<NomenclatureSyncResponse>('/api/menu/sync', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['menu'] })
    },
  })
}

export function useProductRecipe(productId: number | null) {
  return useQuery({
    queryKey: ['menu', 'recipe', productId],
    queryFn: () => api.get<RecipeDetail | null>(`/api/menu/products/${productId}/recipe`),
    enabled: productId != null,
  })
}

export function useSyncRecipes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<RecipeSyncResponse>('/api/menu/recipes/sync', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['menu', 'recipe'] })
    },
  })
}
