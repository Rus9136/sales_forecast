# Shell classes — implementation status

`patterns.md` ссылается на много CSS-классов, но не все из них уже портированы в `frontend/src/styles/shell.css`. Это карта «что готово / что нужно перенести из design source».

## Источники

- **Готово (production):** `frontend/src/styles/shell.css`
- **Design source (read-only, эталон):** `docs/aqniet_site_extracted/design_handoff_sales_forecast/styles/components.css`

Если класса нет в production-файле, бери его из design source — копируй конкретное правило с теми же именами и токенами. **Не сочиняй своё — рискуешь развалить визуальную консистентность.**

## Status table

| Класс | shell.css | components.css (source) | Стратегия использования |
|---|---|---|---|
| `.page` / `.page__header` / `.page__title` / `.page__actions` | ✅ | ✅ | Использовать как есть. |
| `.sidebar*` / `.topbar*` / `.cmdk*` / `.search-trigger` / `.kbd` | ✅ | ✅ | Уже работает через AppLayout. Не трогать. |
| `.kpi` / `.kpi__label` / `.kpi__value` / `.kpi__foot` / `.kpi__spark` | ✅ (минус `__spark`) | ✅ | `.kpi__spark` отсутствует — добавить или просто разместить sparkline через inline style. |
| `.dot` / `.dot--pos|neg|warn|info` | ✅ | ✅ | Готово. |
| `.trend` / `.trend--pos|neg` | ✅ | ✅ | Готово. |
| `.btn-ghost` / `.btn-icon` / `.btn-icon-sm` | ✅ | (как `.btn--ghost` / `.btn--icon`) | Готово. Имена в shell.css слегка отличаются — `btn-ghost`, не `btn--ghost`. |
| `.nav-item*` | ✅ | ✅ | Готово. |
| `.num` / `.mono` / `.tabular` (tabular-nums helper) | ✅ | — | Готово. |
| `.avatar` | ✅ | ✅ | Готово. |
| **`.card` / `.card__header` / `.card__title` / `.card__sub` / `.card__body`** | ❌ | ✅ | **Не портировано.** Использовать shadcn `<Card>` / `<CardHeader>` / `<CardTitle>` — они уже завязаны на токены через `index.css` theme bridge. |
| **`.tbl` / `.table-wrap` / `.table-toolbar` / `.table-scroll` / `.table-footer`** | ❌ | ✅ | **Не портировано.** Варианты: (1) портировать секцию из `components.css` в `shell.css` целиком; (2) пока использовать shadcn `<Table>` + inline-overrides на токенах. Без `.tbl` не получится sticky-thead/sticky-left-column. |
| **`.filters` / `.field-label`** | ❌ | ✅ | **Не портировано.** Можно перенести (правил мало). До этого — обычный `<div className="grid grid-cols-N gap-3">` + shadcn `<Label>` для `.field-label`. |
| **`.chip` / `.chip__close`** | ❌ | ✅ | **Не портировано.** Перенести из source — это короткий блок. |
| **`.badge` / `.badge--pos|neg|warn|accent`** | ❌ | ✅ | **Не портировано.** Альтернатива: shadcn `<Badge>` + variant с `--pos`/`--neg`/`--warn` фоном из токенов. Если нужно один-в-один с дизайном — перенести классы из source. |
| **`.tabs` / `.tab` / `.tab.active`** (underline-стиль) | ❌ | ✅ | **Не портировано.** Перенести при первом использовании. shadcn `<Tabs>` даёт pill-стиль, не подходит для дизайн-эстетики. |
| **`.seg`** (segmented control) | ❌ | ✅ | **Не портировано.** Перенести при первом использовании. |
| **`.empty`** | ❌ | ✅ | **Не портировано.** Использовать `frontend/src/components/shared/empty-state.tsx` или перенести `.empty` из source. |
| **`.pager`** | ❌ | ✅ | **Не портировано.** Использовать shadcn `<Button>` + custom layout до момента порта. |
| **`.input` / `.select`** (raw classes) | ❌ | ✅ | shadcn `<Input>` / `<Select>` уже завязаны на токены. Не нужно портировать raw-классы. |
| **`.skel`** (skeleton) | ❌ | ✅ | shadcn `<Skeleton>` уже есть. |
| **`.heatmap-grid`** | ❌ | ✅ | **Не портировано.** При нужде — перенести + использовать формулу из дизайна (`oklch(0.96 - t*0.34, 0.02 + t*0.13, 162)`). |
| **`.drawer`** | ❌ | ❌ (custom в дизайне) | Пока использовать shadcn `<Dialog>` с правым позиционированием. |
| **`.toast`** | ❌ | ✅ | Пока не используется в проекте. При нужде — `sonner` + темизация через токены. |

## Как переносить класс из design source

1. Открыть `docs/aqniet_site_extracted/design_handoff_sales_forecast/styles/components.css`, найти нужный селектор.
2. Скопировать **всё правило целиком** (включая медиа-запросы и hover/active варианты).
3. Вставить в `frontend/src/styles/shell.css` в логически близкую секцию.
4. Проверить, что все `var(--…)` токены, на которые ссылается правило, существуют в `frontend/src/styles/tokens.css`. Если нет — добавить в обе темы (light + dark) и в accent-варианты.
5. После переноса — обновить эту таблицу: `❌` → `✅`.

## Правило для скилла

При работе с компонентом, где статус `❌`:
- **Сначала** проверить эту таблицу.
- **Потом** решить: портировать класс (если будет повторное использование) или взять fallback-вариант (shadcn / inline).
- **Никогда** не предполагать наличие класса в `shell.css` — `grep '\.имя-класса' frontend/src/styles/shell.css` подтвердит/опровергнет за секунду.
