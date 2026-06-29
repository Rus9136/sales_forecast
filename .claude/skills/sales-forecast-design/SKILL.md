---
name: sales-forecast-design
description: Sales Forecast (aqniet.space) frontend design system — design tokens (OKLCH colors, light/dark themes, 4 accents, 3 density modes), shell layout (sidebar+topbar+CmdK), shadcn/ui primitives, and the "корпоративная панель аналитики" visual language. ALWAYS use this skill — and prefer it over any generic frontend-design skill — when adding or editing anything under `frontend/src/` in this project (pages, screens, components, KPI cards, tables, charts, dialogs, filters, badges, tabs), even when the user just says "сделай страницу X", "добавь форму", "новый компонент", "стили", "оформление", "по дизайну", "перерисуй", "поправь верстку". Also trigger when touching design tokens, themes, sidebar/topbar, or anything that should match the dashboard look. Do NOT trigger for backend code, build/tooling configs (vite.config, tsconfig, eslint, package.json), or for pure logic in `frontend/src/hooks/` and `frontend/src/lib/` that has no JSX.
---

# Sales Forecast — Frontend Design Skill

You are working on the Sales Forecast корпоративная панель аналитики at `aqniet.space`. The visual language is locked — pixel-fidelity to the design handoff at `docs/aqniet_site_extracted/design_handoff_sales_forecast/`. New components must look like they belong to the same product, not a generic shadcn dashboard.

**Stack constraint:** React 19 + TypeScript + Vite + Tailwind CSS 4 + shadcn/ui + TanStack Query + Recharts. No new UI libraries. No `framer-motion` for "fancy" animations — match the existing 80–240 ms transitions.

## Step 1 — Check what already exists before writing anything

The shell, tokens, and primitives are **already implemented**. Reuse them; don't re-create.

| What you need | Where to find it |
|---|---|
| Color/spacing/radius/density tokens | `frontend/src/styles/tokens.css` |
| Layout classes (`.page`, `.kpi`, `.sidebar`, `.topbar`, `.btn-ghost`, `.search-trigger`, `.kbd`, `.dot`, `.trend`) | `frontend/src/styles/shell.css` |
| Theme/accent/density runtime | `frontend/src/contexts/ui-prefs-context.tsx` (`useUIPrefs()`) |
| Sidebar / Topbar / CmdK | `frontend/src/components/layout/{sidebar,topbar,cmdk,app-layout}.tsx` |
| shadcn/ui primitives (Button, Card, Dialog, Tabs, Table, Select, Alert, Badge, Progress, Input, Textarea, AlertDialog, Tooltip, Skeleton, Separator, Label) | `frontend/src/components/ui/` |
| Shared building blocks (DateRangePicker, DepartmentSelect, ConfirmDialog, EmptyState, ErrorAlert, LoadingSpinner) | `frontend/src/components/shared/` |
| Existing pages to mimic | `frontend/src/pages/*.tsx` |
| Original design reference (read-only) | `docs/aqniet_site_extracted/design_handoff_sales_forecast/` |

**Before adding a new component**, grep `frontend/src/components/` for an existing one. If something close exists, extend or compose; don't fork.

## Step 2 — Use design tokens, not hex values

Every color, radius, shadow, and font goes through CSS custom properties so theme/accent switching works automatically. Hard-coded `#3498db` or `oklch(...)` literals in JSX will visibly break dark mode and accent customization.

| Use this | Not this |
|---|---|
| `var(--accent)`, `var(--accent-soft)`, `var(--accent-fg)` | hard-coded green/blue |
| `var(--bg)`, `var(--surface)`, `var(--surface-2)`, `var(--bg-sunken)` | `bg-white`, `bg-slate-50` |
| `var(--text)`, `var(--text-muted)`, `var(--text-subtle)` | `text-gray-600` |
| `var(--border)`, `var(--border-strong)`, `var(--border-faint)` | `border-gray-200` |
| `var(--pos)` / `var(--neg)` / `var(--warn)` / `var(--info)` for semantic state | random green/red |
| `var(--row-h)`, `var(--row-pad-y)` (set by `data-density`) | fixed `h-10` |
| `var(--shadow-sm/md/lg/pop)` | `shadow-md` (Tailwind preset) |
| `var(--radius-sm/md/lg/xl)` | `rounded-lg` w/ wrong scale |

The Tailwind theme in `frontend/src/index.css` already maps `--color-background`, `--color-primary`, etc. to these variables, so utilities like `bg-card`, `text-muted-foreground`, `border-input` work correctly. **Prefer those Tailwind utilities** for layout work, then drop into raw `var(--…)` only when the utility doesn't cover what you need (e.g., specific shell classes, semantic tokens, density-driven heights).

If you need a brand-new token, add it to `tokens.css` (light + dark blocks) instead of inlining a value once.

## Step 3 — Follow the page template

Every screen lives inside `<AppLayout>` (already wired in `App.tsx`). Inside an outlet, the page itself uses `.page` → `.page__header` → body. This is the design's standard frame.

```tsx
export function MyPage() {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Заголовок страницы</h1>
          <span className="sub">Короткое пояснение или период</span>
        </div>
        <div className="page__actions">
          {/* фильтры/экспорт/обновить — кнопки справа */}
        </div>
      </div>

      {/* основной контент: KPI-row → graphs → table */}
    </div>
  )
}
```

For 4-column KPI rows the design uses `display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px`. For shorter pages it's `2fr 1fr` (chart + side panel) or `1fr 1fr 1fr`.

Page max-width is **1600 px**, padding `20px 28px 40px`, content centered with `margin: 0 auto`.

## Step 4 — Patterns that recur on most screens

These appear so often that getting them wrong reads as "wrong product". Read `references/patterns.md` for full snippets, but the highlights:

> **Важно про CSS-классы.** Только часть design-классов (`.kpi`, `.dot`, `.trend`, `.page__*`, shell-классы) уже портирована в `frontend/src/styles/shell.css`. Многие классы из `patterns.md` (`.tbl`, `.card__header`, `.filters`, `.badge--pos`, `.tabs`, `.seg`, `.empty`, `.chip`) ещё **не портированы** — оригиналы лежат в `docs/aqniet_site_extracted/.../components.css` (read-only). Перед использованием класса проверь `references/shell-classes-status.md` и сделай `grep '\.имя' frontend/src/styles/shell.css`. Если класса нет — портируй правило целиком из source ИЛИ возьми эквивалент из shadcn/ui (`<Card>`, `<Table>`, `<Badge>`, `<Tabs>`) на токенах. Не выдумывай свои стили.

- **KPI card** (`.kpi`): label (12 px muted) → value (28 px tabular-nums) → footer with trend (`.trend--pos|--neg`) and "vs пред. период" → optional sparkline (32 px tall). Use Recharts `<LineChart>` with no axes for the sparkline.
- **Tables**: shadcn `<Table>` works, but for the design's "корпоративный" feel apply class `tbl` from `shell.css`. Keep `font-variant-numeric: tabular-nums` on numeric cells (`.num` class). Sticky thead, sticky first column with `box-shadow: 1px 0 0 var(--border-faint)`. Bulk-select chips replace the toolbar when `selected.size > 0`.
- **Filters bar**: `.filters` grid, every field gets a `.field-label` (uppercase 11 px muted). Active filters shown as `.chip` pills with × close.
- **Charts**: Recharts only (we ship it). Line charts use `stroke="var(--accent)"`, fill with `opacity 0.10`, dashed series for прогноз. Bar charts use `var(--accent)` with hover-darken. Grid lines `var(--chart-grid)`, axis text `var(--chart-axis)`.
- **Status badges**: shadcn `<Badge>` + variants. The design uses pill-shaped badges with a leading `.dot` for status indicators. Map: Согласован → `badge--pos`, На проверке → `badge--warn`, Черновик → neutral, Выплачен → `badge--accent`.
- **Dialogs / drawers**: small forms — shadcn `<Dialog>`. Detail panes that slide in from the right (employee/forecast detail) — design uses `.drawer` (custom) but a Dialog with `side="right"` is acceptable until the drawer pattern is needed.
- **Tabs**: design uses underline tabs (`.tabs` + `.tab.active` with `border-bottom-color: var(--accent)`). Match this style rather than shadcn's pill tabs when building tabbed sections (Bonuses page does 4 tabs this way).

## Step 5 — Russian copy, ru-RU formats

All UI text is in Russian. Use existing helpers in `frontend/src/lib/formatters.ts`:

| Helper | Output | Use for |
|---|---|---|
| `formatCurrency(value)` | `1 234 567 ₸` (NBSP separator, ₸ symbol) | Любые суммы в тенге |
| `formatDate(dateStr)` | `30.04.2026` | ru-RU короткая дата |
| `formatDateTime(dateStr)` | `30.04.2026, 14:32` | Дата + время |
| `formatPercent(value)` | `+12,4%` (comma decimal) | Дельты, проценты |
| `toISODate(date)` / `daysAgo(n)` / `daysFromNow(n)` | `YYYY-MM-DD` | Параметры API-запросов |
| `SEGMENT_LABELS`, `TYPE_LABELS`, `LOCATION_TYPE_LABELS`, `SEASONALITY_LABELS`, `MONTH_LABELS` | Russian labels for enums | Селекты, бейджи статусов |

Не дублируй эти функции — импортируй из `@/lib/formatters`.

Don't paraphrase labels — reuse the design's wording: `Подразделения`, `Расчёты бонусов`, `Прогноз по филиалам`, `Сравнение факт / прогноз`, `Ручной ввод KPI`, etc. Sidebar groups: `Аналитика`, `Продажи`, `Прогноз продаж`, `Бонусы`, `Справочники`, `Сервис`, `Администрирование`.

## Step 6 — Don'ts (specific landmines)

- **Don't apply this skill to non-UI work.** Skip for tooling/build configs (`vite.config.ts`, `tsconfig.json`, `package.json`, ESLint), pure data-layer hooks без JSX, или backend (`app/`). Скилл — про визуальную консистентность, а не про любую правку в репо.
- **Don't import from `docs/aqniet_site_extracted/.../src/primitives.jsx`** — that file is reference-only. Recreate any missing widgets using shadcn/ui + Recharts.
- **Don't add a new charting library**. Recharts is already shipped and themed.
- **Don't hard-code `bg-white`, `text-slate-900`, `border-gray-200`**. Use tokens / Tailwind theme utilities.
- **Don't introduce a global state manager**. Server state → TanStack Query. UI state (theme/accent/density/sidebar) → `useUIPrefs()`. Local form state → `useState`.
- **Don't bypass the Sidebar's section filter**. Every nav item declares a `SectionKey` and `hasSection()` decides visibility — adding a new screen means adding a `SectionKey` in `frontend/src/types/auth.ts`, the backend `app/auth_ui.py::AVAILABLE_SECTIONS`, and a `<ProtectedRoute section="…">` route.
- **Don't ship plain `oklch(...)` values inline** — always go through a token, even for temporary one-off colors.
- **Don't disable `font-variant-numeric: tabular-nums`** on number cells. Misaligned digits are the #1 visible regression.
- **Don't change the sidebar collapse breakpoint or topbar height** without updating the matching token (`--sidebar-w`, `--sidebar-w-collapsed` in tokens.css).

## Step 7 — When the user wants a new screen

1. Read the closest existing page in `frontend/src/pages/` and the matching design source in `docs/aqniet_site_extracted/design_handoff_sales_forecast/src/screens/`.
2. Add a `SectionKey`, route in `App.tsx`, sidebar entry in `sidebar.tsx::navSections`. (See pattern in `references/new-screen.md`.)
3. Build the page as `<div className="page"> + page__header + body`.
4. Use shadcn/ui `<Card>`, `<Table>`, `<Tabs>`, `<Dialog>`, `<Button>` for primitives. Use shell classes (`.kpi`, `.btn-ghost`, `.dot`, `.trend`) where shadcn doesn't have a direct equivalent.
5. Wire data through a TanStack Query hook in `frontend/src/hooks/use-*.ts`.
6. Run `pnpm build` from `frontend/`. Check the gzipped CSS hasn't ballooned (>10% growth = something wasn't reused).

## Reference files

Detail lives in `references/`. Read the relevant one when needed — these aren't loaded by default to keep the skill's context cost low.

- **`references/tokens.md`** — full token table with values + when to use each. Read when adding a new token or when picking colors for a new state.
- **`references/patterns.md`** — copy-paste-ready JSX snippets for KPI rows, tables with bulk-select, filters bar, line/bar charts, drawers, segmented controls. Read when building a new screen. **Сначала проверь `shell-classes-status.md` — не все классы из сниппетов уже портированы.**
- **`references/components-map.md`** — which shadcn/ui or shell class corresponds to each design-handoff primitive. Read when porting from `design_handoff_sales_forecast/src/`.
- **`references/new-screen.md`** — exact checklist for adding a route + sidebar entry + section key + protected route. Read when creating any new page.
- **`references/shell-classes-status.md`** — карта «что уже в shell.css / что ещё нужно портировать из design source». Read **до** использования любого класса из patterns.md, чтобы не наткнуться на отсутствующий стиль.

## Quick sanity check before declaring "done"

- Light **and** dark themes both look right? (Toggle the moon/sun in topbar.)
- Switching accent to `indigo` / `amber` / `slate` doesn't break? (Set `data-accent` on `<html>`.)
- Density `compact` / `cozy` / `spacious` all work for tables?
- Sidebar collapse mode shows just icons without text overflow?
- All numeric cells have `tabular-nums`?
- Russian copy matches the design wording?
- No hard-coded hex / oklch literals in the JSX you added?

If any answer is no, fix it before reporting completion.
