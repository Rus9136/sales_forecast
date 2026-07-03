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
  applied: 'Применена',
  expired: 'Истекла',
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return '—'
  return STATUS_LABELS[status as RecommendationStatus] ?? status
}

/** shadcn Badge variant per recommendation status (applied → success/green). */
export function statusBadgeVariant(
  status: string | null | undefined,
): 'default' | 'secondary' | 'destructive' | 'success' | 'outline' {
  if (status === 'approved') return 'default'
  if (status === 'applied') return 'success'
  if (status === 'rejected') return 'destructive'
  if (status === 'expired') return 'outline'
  return 'secondary'
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

/** Надёжность оценки спроса словами — грейд остаётся рядом («Высокая · A»). */
export const GRADE_WORDS: Record<string, string> = {
  A: 'Высокая',
  B: 'Хорошая',
  C: 'Низкая',
  D: 'Минимальная',
}

export function gradeWord(grade: string | null | undefined): string {
  if (!grade) return 'Нет оценки'
  return GRADE_WORDS[grade] ?? grade
}

/** Одно предложение смысла каждой роли меню — показывается прямо в карточках. */
export const MENU_ROLE_DESCRIPTIONS: Record<MenuRole, string> = {
  premium_anchor: 'Дорогие статусные блюда. Задают планку цен, меняем осторожно.',
  margin_driver: 'Главный источник прибыли. Основная зона работы оптимизатора.',
  traffic_driver: 'Ходовые блюда, ради которых приходят. Цену почти не трогаем.',
  image_rare: 'Редкие продажи, важны для образа меню. Округление до 100 ₸.',
  tail: 'Мало продаж и прибыли. Кандидаты на пересмотр или вывод из меню.',
}

/** Человекочитаемые названия ограничений оптимизатора (constraints_applied). */
export const CONSTRAINT_LABELS: Record<string, string> = {
  min_margin: 'мин. маржа',
  max_step: 'шаг ≤ лимита',
  min_frequency: 'частота изменений',
  rounding: 'округление',
  no_decrease_anchor: 'якорь: только вверх',
  no_psychological: 'без «…9» окончаний',
  stop_list: 'стоп-лист',
  max_changes_per_cycle: 'лимит за цикл',
  cumulative_cap: 'потолок за 90 дней',
  min_competitive_idx: 'конкурентный индекс',
}

export function constraintLabel(code: string): string {
  return CONSTRAINT_LABELS[code] ?? code
}

/** Локализация действий журнала аудита. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  approved: 'Утверждена',
  rejected: 'Отклонена',
  applied: 'Применена',
  expired: 'Истекла',
  superseded: 'Заменена новой',
  create: 'Создание',
  update: 'Изменение',
  delete: 'Удаление',
  generate: 'Генерация',
  freeze: 'Фиксация базы',
  override: 'Смена роли',
}

export function auditActionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action
}

/** Человекочитаемые ключи details в журнале аудита. */
export const AUDIT_DETAIL_LABELS: Record<string, string> = {
  comment: 'комментарий',
  reason: 'причина',
  batch: 'массовое действие',
  manual_role: 'роль вручную',
  effective_role: 'действующая роль',
  rule_type: 'правило',
  scope_type: 'уровень',
  scope_id: 'объект',
  params: 'параметры',
  weeks: 'недель',
  departments: 'точек',
  force: 'перезапись',
  baseline_from: 'с',
  baseline_to: 'по',
  n_requested: 'запрошено',
  n_created: 'создано',
  delta_pct: 'Δ цены %',
  status: 'статус',
}
