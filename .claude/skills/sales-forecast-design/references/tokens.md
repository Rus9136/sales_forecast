# Design tokens — reference

Source of truth: `frontend/src/styles/tokens.css`. This file is a flat lookup table — read it when you need to pick a color or know which token covers a given role.

The tokens are CSS custom properties on `:root` and per-theme overrides on `[data-theme="light|dark"]`. Theme/accent/density are set on `<html>` by `UIPrefsProvider` from `localStorage["sf.ui-prefs"]`.

## Colors

### Backgrounds
| Token | Light | Dark | Use for |
|---|---|---|---|
| `--bg` | near-white slate | near-black slate | Page background, behind everything |
| `--bg-elev` | `#fff` | dark surface | Elevated content above bg (rare) |
| `--bg-sunken` | slightly darker than bg | darker than bg | Inset panels (filters bar bg, segmented control track, table thead in some places) |
| `--bg-hover` | hover state for bg | hover state | Row hover, ghost button hover |
| `--bg-active` | pressed/active | pressed/active | Pressed states |
| `--surface` | `#fff` | elevated dark | Cards, dialogs, dropdowns, the main "paper" |
| `--surface-2` | very light slate | slightly elevated | Toolbar inside cards, table thead |

### Borders
| Token | Use |
|---|---|
| `--border` | Default 1px borders (cards, inputs, table rows) |
| `--border-strong` | Hover state on inputs, scrollbar thumb |
| `--border-faint` | Lightest divider — between table rows, between top-list rows |

### Text
| Token | Use |
|---|---|
| `--text` | Primary copy, headings, KPI values |
| `--text-muted` | Labels, secondary info, table headers |
| `--text-subtle` | Placeholders, breadcrumb separators, kbd |
| `--text-inverse` | Text on accent backgrounds (rarely needed) |

### Sidebar (separate scope)
| Token | Use |
|---|---|
| `--sidebar-bg` | Sidebar panel background |
| `--sidebar-border` | Right border of sidebar |
| `--sidebar-text` | Default nav-item color |
| `--sidebar-text-active` | Active nav-item, brand name |
| `--sidebar-item-hover` | Hovered nav-item background |
| `--sidebar-item-active` | Active nav-item background (subtle elevation) |

### Topbar
| Token | Use |
|---|---|
| `--topbar-bg` | Translucent topbar background (works with backdrop-blur) |

### Tables / charts
| Token | Use |
|---|---|
| `--row-stripe` | Striped row alternate (currently unused — design is non-striped) |
| `--row-hover` | Hovered table row |
| `--chart-grid` | Recharts grid lines |
| `--chart-axis` | Recharts axis text/ticks |
| `--skel` | Skeleton placeholder base color |

## Accent

`--accent`, `--accent-fg`, `--accent-soft`, `--accent-soft-fg`, `--accent-ring`. Switched by `data-accent="emerald|indigo|amber|slate"` on `<html>`. Default is `emerald` (for "рост, успех" semantics).

- **emerald** (default) — изумрудный, для роста/положительной динамики
- **indigo** — корпоративный синий
- **amber** — янтарный (используется и для предупреждений в semantic, не путать)
- **slate** — нейтральный, для документального режима

`--accent-soft` is the pastel chip background; `--accent-soft-fg` is the foreground that has enough contrast on it. Both flip in dark mode (chip becomes a darker mid-tone, fg stays light).

## Semantic state

| Token | Hue | Use |
|---|---|---|
| `--pos` | green ~162° | Рост, успех, +Х%, "согласован" |
| `--neg` | red ~25° | Падение, ошибка, отклонение -Х%, "отклонён" |
| `--warn` | amber ~75° | Предупреждение, "на проверке", under-plan |
| `--info` | blue ~240° | Нейтральная информация |

For badges with backgrounds, the design hard-codes `oklch(0.95 0.04 …)` for light bg and `oklch(0.32 0.07 …)` for dark — see the `.badge--pos` / `.badge--neg` / `.badge--warn` rules in `shell.css` (currently in design source `components.css`). Use the class, don't reinvent the calc.

## Spacing

`--sp-1` through `--sp-9` = 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 56 px. Tailwind's `p-1`/`gap-2` etc. don't map 1:1 to these — when you need exact design spacing, prefer the token. For everyday spacing, Tailwind utilities (`p-4`, `gap-3`) are fine — they all hit "design grid" values anyway.

## Radius

`--radius-xs|sm|md|lg|xl` = 4 / 6 / 8 / 12 / 16 px. Cards use `--radius-lg` (12 px). Buttons and inputs use `--radius-md` (8 px). Pills/badges use `999px`.

## Density

| `data-density` | `--row-h` | `--row-pad-y` |
|---|---|---|
| `compact` | 32 px | 4 px |
| `cozy` (default) | 40 px | 8 px |
| `spacious` | 52 px | 12 px |

Apply to `td` height + padding so the user-controlled density actually changes table rows. Pages don't need to do anything special — the `.tbl tbody td` rule reads these vars.

## Sidebar geometry

- `--sidebar-w` = 240 px (expanded)
- `--sidebar-w-collapsed` = 64 px

## Topbar geometry

- Topbar height fixed at 56 px (in `.topbar` rule)

## Shadows

| Token | Use |
|---|---|
| `--shadow-sm` | KPI cards subtle lift, primary buttons inner highlight |
| `--shadow-md` | Default card elevation if needed (cards usually use border instead) |
| `--shadow-lg` | Modal/dialog/cmdk drop shadow |
| `--shadow-pop` | Popovers, tooltips |

## Typography

- `--font-sans`: Geist (loaded from Google Fonts in `index.css`)
- `--font-mono`: Geist Mono (для кодов, чисел в таблицах если нужно подчеркнуть)

Sizes:
- Body 14 px / line-height 1.45
- h1 22 px (page title)
- h2 18 px (card title sometimes)
- h3 15 px
- KPI value 28 px
- Card title 13 px (`.card__title`)
- Label uppercase 11–12 px (`.field-label`, `.kpi__label`)

Always include `font-variant-numeric: tabular-nums` on numeric content (.num, .mono, .tabular helper classes do this).

## Easing

`--ease: cubic-bezier(0.2, 0.7, 0.2, 1)` — single ease curve for the whole product. Durations 80–240 ms (hover 80–120, drawer/cmdk 200–240).

## When to add a new token

You shouldn't need to often. Add a token when:
- The same `oklch(...)` literal would appear ≥3 times across the codebase
- The value needs to differ between light/dark themes
- It represents a semantic role ("approved" badge bg) rather than a one-off color

To add: write the new var in **both** `:root` (or one of the theme blocks) **and** any accent variant blocks that should override it. Then reference it from `shell.css` or component styles. Don't put the value in JSX.
