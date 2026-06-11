import type { MenuRole, RecommendationStatus } from '@/types/pricing'

export const MENU_ROLE_LABELS: Record<MenuRole, string> = {
  premium_anchor: 'Премиум-якорь',
  margin_driver: 'Драйвер маржи',
  traffic_driver: 'Драйвер трафика',
  tail: 'Хвост',
  image_rare: 'Имиджевые',
}

export function menuRoleLabel(role: string | null | undefined): string {
  if (!role) return '—'
  return MENU_ROLE_LABELS[role as MenuRole] ?? role
}

/** Semantic token color per menu role (for badges/bars). */
export const MENU_ROLE_COLOR: Record<MenuRole, string> = {
  premium_anchor: 'var(--accent)',
  margin_driver: 'var(--pos)',
  traffic_driver: 'var(--info)',
  image_rare: 'var(--warn)',
  tail: 'var(--text-subtle)',
}

export function menuRoleColor(role: string | null | undefined): string {
  if (!role) return 'var(--text-subtle)'
  return MENU_ROLE_COLOR[role as MenuRole] ?? 'var(--text-subtle)'
}

export const STATUS_LABELS: Record<RecommendationStatus, string> = {
  new: 'Новая',
  approved: 'Утверждена',
  rejected: 'Отклонена',
  expired: 'Истекла',
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return '—'
  return STATUS_LABELS[status as RecommendationStatus] ?? status
}

/** Semantic token color per reliability grade (A best → D weakest). */
export const GRADE_COLOR: Record<string, string> = {
  A: 'var(--pos)',
  B: 'var(--info)',
  C: 'var(--warn)',
  D: 'var(--neg)',
}

export function gradeColor(grade: string | null | undefined): string {
  if (!grade) return 'var(--text-subtle)'
  return GRADE_COLOR[grade] ?? 'var(--text-subtle)'
}
