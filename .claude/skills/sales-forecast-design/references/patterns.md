# Common UI patterns — copy-paste reference

These are the design-handoff patterns translated into our stack (React 19 + TS + shadcn/ui + Tailwind 4 + Recharts). The goal is to keep visual consistency without re-inventing primitives.

## ⚠️ Status legend

Не все CSS-классы из этих сниппетов уже портированы. Перед копированием проверь `references/shell-classes-status.md`. Метки:

- 🟢 **Ready** — все классы есть в `frontend/src/styles/shell.css`. Снять и вставить.
- 🟡 **Partial** — часть классов готова, часть нужно дополнить. Альтернатива: shadcn/ui + токены.
- 🔴 **Needs port** — основной класс ещё не в shell.css. Перед использованием либо портируй правило из `docs/aqniet_site_extracted/.../components.css`, либо возьми shadcn-эквивалент.

| Sect. | Status | Why |
|---|---|---|
| Page frame | 🟢 | `.page*` готов |
| KPI row | 🟢 | `.kpi*` + `.trend*` готовы (минус `.kpi__spark` — добавить или inline) |
| Card with header + chart | 🔴 | `.card*` нет в shell.css → использовать shadcn `<Card>` |
| Filters bar | 🔴 | `.filters` / `.field-label` нужно портировать |
| Table | 🔴 | `.tbl` / `.table-*` нужно портировать или заменить на shadcn `<Table>` |
| Status badge with dot | 🟡 | `.dot*` готовы, `.badge--*` нет — использовать shadcn `<Badge>` или портировать |
| Tabs (underline) | 🔴 | `.tabs` / `.tab` нужно портировать (shadcn даёт pill — не подходит) |
| Segmented control | 🔴 | `.seg` нужно портировать |
| Trend indicator | 🟢 | `.trend*` готовы |
| Forecast row | 🔴 | `.forecast-rows`, `.fr-row`, `.meter` — кастомные, нужно создавать |
| Empty state | 🟡 | `.empty` нет, но есть `frontend/src/components/shared/empty-state.tsx` |
| Drawer | 🔴 | Нет ни в shell.css, ни в design source — пока shadcn `<Dialog>` |

## Page frame

Every screen looks like this. The `.page` class applies max-width 1600 px and centered padding.

```tsx
import { Button } from '@/components/ui/button'
import { Download, Filter, RefreshCw } from 'lucide-react'

export function MyPage() {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Заголовок</h1>
          <span className="sub">Период · фильтр</span>
        </div>
        <div className="page__actions">
          <Button variant="outline" size="sm"><Filter className="h-3.5 w-3.5" /> Фильтры</Button>
          <Button variant="outline" size="sm"><Download className="h-3.5 w-3.5" /> Экспорт</Button>
          <Button size="sm"><RefreshCw className="h-3.5 w-3.5" /> Обновить</Button>
        </div>
      </div>

      {/* body — обычно: KPI-row → graph card → table-wrap */}
    </div>
  )
}
```

## KPI row (4 cards)

```tsx
import { ArrowDown, ArrowUp } from 'lucide-react'
import { LineChart, Line } from 'recharts'

interface Kpi {
  label: string
  value: string  // "1 234 567 ₸" — already formatted
  delta: number  // % change vs previous period
  spark: number[]
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const positive = kpi.delta >= 0
  const sparkData = kpi.spark.map((v, i) => ({ i, v }))
  return (
    <div className="kpi">
      <div className="kpi__label">{kpi.label}</div>
      <div className="kpi__value">{kpi.value}</div>
      <div className="kpi__foot">
        <span className={'trend ' + (positive ? 'trend--pos' : 'trend--neg')}>
          {positive ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
          {positive ? '+' : ''}{kpi.delta.toFixed(1).replace('.', ',')}%
        </span>
        <span style={{ fontSize: 11 }}>vs пред. период</span>
      </div>
      <div className="kpi__spark">
        <LineChart width={120} height={32} data={sparkData}>
          <Line type="monotone" dataKey="v" stroke="var(--accent)" strokeWidth={1.5} dot={false} />
        </LineChart>
      </div>
    </div>
  )
}

// Usage:
<div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
  {kpis.map((k, i) => <KpiCard key={i} kpi={k} />)}
</div>
```

## Card with header + chart

```tsx
<div className="card">
  <div className="card__header">
    <div>
      <div className="card__title">Динамика продаж</div>
      <div className="card__sub">Факт vs прогноз</div>
    </div>
    {/* optional segmented control on right */}
  </div>
  <div style={{ padding: '10px 14px 14px' }}>
    <ResponsiveContainer width="100%" height={280}>
      <RechartsLineChart data={trendData}>
        <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
        <XAxis dataKey="label" stroke="var(--chart-axis)" tick={{ fontSize: 11 }} />
        <YAxis stroke="var(--chart-axis)" tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} />
        <Line dataKey="fact" stroke="var(--accent)" strokeWidth={2} dot={false} name="Факт" />
        <Line dataKey="forecast" stroke="var(--text-subtle)" strokeWidth={2} strokeDasharray="4 4" dot={false} name="Прогноз" />
      </RechartsLineChart>
    </ResponsiveContainer>
  </div>
</div>
```

For an area-fill under the line, add `<Area dataKey="fact" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.10} />` and switch to `<AreaChart>`.

## Filters bar

```tsx
<div className="filters">
  <div className="field">
    <label className="field-label">Период</label>
    <DateRangePicker value={range} onChange={setRange} />
  </div>
  <div className="field">
    <label className="field-label">Подразделение</label>
    <DepartmentSelect value={dept} onChange={setDept} />
  </div>
  <div className="actions">
    <Button variant="outline" size="sm">Сбросить</Button>
    <Button size="sm">Применить</Button>
  </div>
</div>
```

Active filter chips below (when filters are applied):

```tsx
<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
  <span className="chip">
    Период: {fmtDate(range.from)} — {fmtDate(range.to)}
    <span className="chip__close" onClick={clearRange}>×</span>
  </span>
</div>
```

## Table with sticky thead, sortable columns, bulk-select 🔴

For the design's "корпоративная таблица" feel, use the `.tbl` class. **Сейчас этого класса в `shell.css` нет** — оригинал лежит в `docs/aqniet_site_extracted/design_handoff_sales_forecast/styles/components.css` (искать секцию `.tbl`, `.table-wrap`, `.table-toolbar`, `.table-scroll`, `.table-footer`). Перед использованием сниппета ниже либо портируй эту секцию целиком в `shell.css`, либо замени на shadcn `<Table>` с inline-стилями на токенах (sticky-thead через `position: sticky; top: 0; background: var(--surface-2)`).

```tsx
<div className="table-wrap">
  <div className="table-toolbar">
    {selected.size === 0 ? (
      <>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{rows.length} строк</span>
        <div className="spacer" />
        <Button size="sm" variant="outline">Экспорт</Button>
      </>
    ) : (
      <>
        <span style={{ fontSize: 13 }}>Выбрано: {selected.size}</span>
        <div className="spacer" />
        <Button size="sm" variant="outline">Назначить роль</Button>
        <Button size="sm" variant="destructive">Удалить</Button>
      </>
    )}
  </div>

  <div className="table-scroll">
    <table className="tbl">
      <thead>
        <tr>
          <th className="checkbox-cell stick-l">
            <Checkbox
              checked={selected.size === rows.length}
              onCheckedChange={(v) => setSelected(new Set(v ? rows.map(r => r.id) : []))}
            />
          </th>
          <th className={'sortable stick-l ' + (sort.k === 'name' ? 'sorted' : '')}
              onClick={() => onSort('name')}>
            Название <span className="sort">↕</span>
          </th>
          <th className="num">Сумма</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <tr key={row.id} className={selected.has(row.id) ? 'selected' : ''}>
            <td className="checkbox-cell stick-l">
              <Checkbox checked={selected.has(row.id)} onCheckedChange={() => toggle(row.id)} />
            </td>
            <td className="stick-l">{row.name}</td>
            <td className="num">{fmtKZT(row.sum)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>

  <div className="table-footer">
    <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} из {total}</span>
    <div className="spacer" />
    {/* pager */}
  </div>
</div>
```

## Status badge with dot

```tsx
const statusClass: Record<string, string> = {
  'Согласован': 'badge--pos',
  'На проверке': 'badge--warn',
  'Черновик': '',
  'Выплачен': 'badge--accent',
  'Отклонён': 'badge--neg',
}

<span className={'badge ' + (statusClass[row.status] ?? '')}>
  <span className={'dot ' + (
    row.status === 'Согласован' ? 'dot--pos' :
    row.status === 'На проверке' ? 'dot--warn' :
    row.status === 'Отклонён' ? 'dot--neg' : ''
  )} />
  {row.status}
</span>
```

## Tabs (underline style)

Use the `.tabs` / `.tab` classes — shadcn's pill-tabs don't match the design here.

```tsx
const [tab, setTab] = useState<'calc' | 'scheme' | 'kpi' | 'plan'>('calc')

<div className="tabs">
  <button className={'tab ' + (tab === 'calc' ? 'active' : '')} onClick={() => setTab('calc')}>
    Расчёты бонусов
  </button>
  <button className={'tab ' + (tab === 'scheme' ? 'active' : '')} onClick={() => setTab('scheme')}>
    Схемы расчёта
  </button>
  {/* … */}
</div>

{tab === 'calc' && <CalcTab />}
```

## Segmented control

```tsx
<div className="seg">
  <button className={range === 7 ? 'active' : ''} onClick={() => setRange(7)}>7 дней</button>
  <button className={range === 30 ? 'active' : ''} onClick={() => setRange(30)}>30 дней</button>
  <button className={range === 90 ? 'active' : ''} onClick={() => setRange(90)}>90 дней</button>
</div>
```

## Trend indicator inline

```tsx
<span className={'trend ' + (delta >= 0 ? 'trend--pos' : 'trend--neg')}>
  {delta >= 0 ? '+' : ''}{delta.toFixed(1).replace('.', ',')}%
</span>
```

## Forecast row (filiale list with meter bar)

```tsx
<div className="card">
  <div className="card__header">
    <div className="card__title">Прогноз по филиалам</div>
  </div>
  <div className="forecast-rows">
    {branches.map((b) => {
      const ratio = b.fact / b.plan
      const meterClass = ratio > 1.05 ? 'over' : ratio < 0.95 ? 'under' : ''
      return (
        <div key={b.id} className="fr-row">
          <div className="nm">
            <b>{b.name}</b>
            <div className="sub">{b.city} · {b.network}</div>
          </div>
          <div className="num">{fmtKZT(b.plan)}</div>
          <div className="num">{fmtKZT(b.fact)}</div>
          <div className="meter"><i className={meterClass} style={{ width: `${Math.min(100, ratio * 100)}%` }} /></div>
          <div className={'delta ' + (ratio >= 1 ? 'trend--pos' : 'trend--neg')}>
            {((ratio - 1) * 100).toFixed(1).replace('.', ',')}%
          </div>
        </div>
      )
    })}
  </div>
</div>
```

## Empty state

```tsx
<div className="empty">
  <div className="icon-wrap"><Database size={20} /></div>
  <div style={{ fontSize: 13 }}>Нет данных за выбранный период</div>
  <div style={{ fontSize: 12, color: 'var(--text-subtle)', marginTop: 4 }}>
    Попробуйте изменить фильтры или синхронизировать данные
  </div>
</div>
```

## Drawer (right-side detail panel)

The design has a custom `.drawer` for clicking a row to inspect. For now, use shadcn `<Dialog>` — the drawer pattern can be added when there's a real screen that needs it. The dialog should be styled with `width: min(540px, 92vw)` and slid from right; if shadcn's dialog can't, fall through to a custom overlay that uses the `.drawer` class.
