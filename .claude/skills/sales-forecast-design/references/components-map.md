# Components map: design-handoff → our stack

When porting a screen from `docs/aqniet_site_extracted/design_handoff_sales_forecast/`, replace the design's primitives with our existing components. Do **not** copy `src/primitives.jsx` — that's reference-only.

## Lookup table

| Design source | Our equivalent | Notes |
|---|---|---|
| `<Icon name="..." />` from `src/icons.jsx` | `lucide-react` icons | Pick the closest Lucide icon. The design's icon set was custom 16×16 outlines — Lucide's defaults match (`stroke-width: 1.5`). |
| `Sidebar` / `Topbar` / `CmdK` from `src/shell.jsx` | `frontend/src/components/layout/{sidebar,topbar,cmdk}.tsx` | Already implemented, fully functional. Don't add a second copy. |
| `<LineChart series=...>` from `src/primitives.jsx` | `recharts` `<LineChart>`, `<AreaChart>` | See `patterns.md` for color/styling. |
| `<Bars>` (bar chart) | `recharts` `<BarChart>` with `<Bar fill="var(--accent)" />` | Hover-darken via `<Bar onMouseEnter>` is overkill — Recharts default is fine. |
| `<Sparkline>` | `recharts` `<LineChart>` with no axes/grid, `width={120} height={32}` | See KPI card pattern. |
| `<Checkbox>` (custom SVG) | `frontend/src/components/ui/` doesn't have one yet — use `@radix-ui/react-checkbox` or build a minimal one matching `.checkbox` class | If you need indeterminate state for table headers, the radix one supports it. |
| `<Pager>` | Build with shadcn `<Button>` + the `.pager .page` classes | Or use a small inline pager — see existing usage in `pages/` if present. |
| `<ThSort>` + `useSortable` | Plain `<th onClick>` with class `sortable sorted` and a `↕` indicator. State via `useState<{k: string, d: 'asc' \| 'desc'}>`. | Don't pull in tanstack-table for simple cases. |
| `.btn` / `.btn--primary` / `.btn--ghost` | shadcn `<Button>` with `variant="default" \| "outline" \| "ghost"`. | shadcn's `default` ≈ `--primary` (uses `--color-primary` which maps to `--accent`). |
| `.btn--icon` | `<Button size="icon">` | Or pure `.btn-ghost.btn-icon` from shell.css when you need the design's exact 32×32 / 28×28 sizes. |
| `.input` / `.select` | shadcn `<Input>` / `<Select>` | Their default styling now reads from our tokens via the index.css theme bridge. |
| `.search` (in topbar) | `.search-trigger` class + onClick → CmdK | Already implemented as `Topbar`. |
| `.kbd` | `<span className="kbd">⌘ K</span>` | The class is in `shell.css`. |
| `.card` / `.card__header` / `.card__title` / `.card__sub` / `.card__body` | shadcn `<Card>` / `<CardHeader>` / `<CardTitle>` / `<CardDescription>` / `<CardContent>` | Both work; pick one per page and stick with it. The raw classes are smaller and match the design 1:1. |
| `.badge` / `.badge--pos` / `.badge--neg` / `.badge--warn` / `.badge--accent` | shadcn `<Badge>` + variants OR raw `<span className="badge ...">` | The shell.css badge classes have the OKLCH semantic colors baked in — easier to use directly than configuring Badge variants. |
| `.dot` / `.dot--pos|neg|warn|info` | Raw `<span className="dot ..." />` | 6×6 colored circle. Used as a status indicator next to text. |
| `.chip` / `.chip__close` | Raw `<span className="chip">` for filter chips | Don't use Badge for filter pills — chips have a close button slot. |
| `.seg` (segmented control) | Raw `<div className="seg">` with `<button class="active">` | shadcn doesn't have one. ToggleGroup from radix can work but the raw class is closer to design. |
| `.tabs` / `.tab` (underline tabs) | Raw classes (in shell.css) — not shadcn `<Tabs>` | shadcn's Tabs uses pill style; use `.tabs/.tab` for underline. |
| `.tbl` (table with sticky thead, hover, sticky-left col) | Raw `<table className="tbl">` | shadcn `<Table>` doesn't do sticky-thead well; the raw class does. |
| `.kpi` / `.kpi__label` / `.kpi__value` / `.kpi__foot` / `.kpi__spark` | Raw classes from shell.css | Don't wrap in shadcn `<Card>` — the design's KPI is a distinct primitive. |
| `.heatmap` (7×24 day-of-week × hour) | Build with CSS grid using `.heatmap` class | See design's `Dashboard.jsx` for the cell coloring formula (`oklch(0.96 - t*0.34, 0.02 + t*0.13, 162)`). |
| `.empty` (empty state) | Raw `<div className="empty">` with an icon-wrap | We also have `frontend/src/components/shared/empty-state.tsx` — pick whichever fits. |
| `.toast` | shadcn doesn't ship a toast; if needed, add `sonner` and theme it via tokens | Not currently used. |
| `.tweaks-panel` / `TweakSection` / `TweakRadio` | `frontend/src/contexts/ui-prefs-context.tsx` covers the runtime; build a `<SettingsDialog>` or `/settings` page if you need a UI for theme/accent/density | Currently no UI surface for it; the topbar only has a theme toggle. |
| `.drawer` (right-side slide-in) | Use shadcn `<Dialog>` with `side="right"` if the variant is added, else a custom overlay using the `.drawer` class | No production usage yet. |
| `<TweaksPanel>` (the absolute-positioned overlay panel for design tweaks) | **Do not port** | This was a hot-reload tool for the design prototype only. |

## Things to **not** port

- `src/data.jsx` — generated mock data. Never use this in the app; pull real data from FastAPI via TanStack Query hooks.
- `tweaks-panel.jsx` — design-prototype harness for live tweaking; not a production primitive.
- The hand-rolled SVG `LineChart` / `Bars` / `Sparkline` from `primitives.jsx` — Recharts is already shipped and themed.
- The design's custom `<Checkbox>` SVG — use Radix Checkbox.
- Any imports from `window.Sidebar` / `window.Topbar` / `window.CmdK` (those are Babel-inline globals, not real modules).

## When the closest equivalent is "build it custom"

If a design primitive doesn't have a shadcn counterpart and isn't covered by `shell.css`:

1. Decide whether to add it to `shell.css` (if it's reusable) or inline it (one-off).
2. Use only design tokens — no hex / inline `oklch()`.
3. Match transitions (80–240 ms with `var(--ease)`).
4. Add the corresponding entry to this map after merging.
