export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '—'
  return Math.round(value).toLocaleString('ru-RU') + ' ₸'
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('ru-RU')
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ru-RU')
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toFixed(1) + '%'
}

export function toISODate(date: Date): string {
  return date.toISOString().split('T')[0]
}

export function daysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return toISODate(d)
}

export function daysFromNow(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return toISODate(d)
}

export const SEGMENT_LABELS: Record<string, string> = {
  restaurant: 'Ресторан',
  coffeehouse: 'Кофейня',
  confectionery: 'Кондитерская',
  food_court: 'Фуд-корт',
  store: 'Магазин',
  fast_food: 'Фаст-фуд',
  bakery: 'Пекарня',
  cafe: 'Кафе',
  bar: 'Бар',
}

export const TYPE_LABELS: Record<string, string> = {
  DEPARTMENT: 'Подразделение',
  JURPERSON: 'Юр. лицо',
  CORPORATION: 'Корпорация',
}

export const LOCATION_TYPE_LABELS: Record<string, string> = {
  city_center: 'Городской центр',
  mall: 'Торговый центр',
  business_district: 'Бизнес-район',
  resort_mountain: 'Резорт (горы)',
  resort_lake: 'Резорт (озеро)',
  visit_center: 'Визит-центр',
  other: 'Другое',
}

export const SEASONALITY_LABELS: Record<string, string> = {
  none: 'Нет',
  low: 'Слабая',
  medium: 'Средняя',
  high: 'Сильная',
}

export const MONTH_LABELS: { value: number; label: string }[] = [
  { value: 1, label: 'Январь' },
  { value: 2, label: 'Февраль' },
  { value: 3, label: 'Март' },
  { value: 4, label: 'Апрель' },
  { value: 5, label: 'Май' },
  { value: 6, label: 'Июнь' },
  { value: 7, label: 'Июль' },
  { value: 8, label: 'Август' },
  { value: 9, label: 'Сентябрь' },
  { value: 10, label: 'Октябрь' },
  { value: 11, label: 'Ноябрь' },
  { value: 12, label: 'Декабрь' },
]
