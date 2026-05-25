// Mapping iiko source hostnames → human-readable labels.
// `iiko_source_domain` is stored as a bare hostname (see backfill script and
// loader). When a new iiko server is added, extend both `IIKO_SOURCE_LABELS`
// and the `KNOWN_IIKO_SOURCES` order (which controls dropdown ordering).
//
// If a hostname is not in the map, `iikoSourceLabel` returns the host as-is so
// nothing breaks for a freshly added domain — it just looks ugly until labeled.

export const IIKO_SOURCE_LABELS: Record<string, string> = {
  'sandy-co-co.iiko.it': 'Сандык',
  'madlen-group-so.iiko.it': 'Мадлен',
}

export const KNOWN_IIKO_SOURCES: string[] = [
  'sandy-co-co.iiko.it',
  'madlen-group-so.iiko.it',
]

export function iikoSourceLabel(host: string | null | undefined): string {
  if (!host) return '—'
  return IIKO_SOURCE_LABELS[host] ?? host
}
