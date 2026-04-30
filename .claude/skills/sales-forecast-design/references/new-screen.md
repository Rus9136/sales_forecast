# Adding a new screen — checklist

Adding a route requires changes in **3 places** so the section-based RBAC stays consistent. Skipping any of them either breaks build or makes the page invisible/inaccessible.

## 1. Pick a section key

`SectionKey` is the auth surface — the user's role lists which sections they can see, and the sidebar + protected routes filter on it.

**Add the new key in three places (must be identical in all three):**

1. `frontend/src/types/auth.ts` — extend the `SectionKey` union type.
2. `app/auth_ui.py::AVAILABLE_SECTIONS` — add the same string. The backend uses this list to validate role updates.
3. Decide the convention: dotted notation for grouped pages (`bonus.calculations`, `sales.daily`), flat for standalone (`departments`, `sync`).

Example: a new "AI диагностика" page → key `ai.diagnostics`.

## 2. Backend route + endpoint (if needed)

If the page needs new data, add the FastAPI router and migration first. See existing routers in `app/routers/` for shape. New tables → write a migration in `migrations/`.

## 3. Frontend hook (TanStack Query)

Create `frontend/src/hooks/use-<feature>.ts` with the queries/mutations the page needs. Pattern:

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export function useFooList() {
  return useQuery({
    queryKey: ['foo', 'list'],
    queryFn: () => api.get<FooListResponse>('/api/foo/'),
  })
}

export function useFooMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: FooCreate) => api.post('/api/foo/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['foo'] }),
  })
}
```

Type the responses in `frontend/src/types/<feature>.ts`.

## 4. Page component

Create `frontend/src/pages/<feature>-page.tsx`. Use the page frame from `patterns.md`:

```tsx
export function MyFeaturePage() {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Название</h1>
          <span className="sub">Подзаголовок</span>
        </div>
        <div className="page__actions">{/* кнопки */}</div>
      </div>
      {/* body */}
    </div>
  )
}
```

## 5. Route in App.tsx

```tsx
<Route element={<ProtectedRoute section="ai.diagnostics" />}>
  <Route path="/ai-diagnostics" element={<AIDiagnosticsPage />} />
</Route>
```

Add the import at the top in alphabetical-ish order with the other page imports.

## 6. Sidebar nav entry

Edit `frontend/src/components/layout/sidebar.tsx::navSections`. Insert into the right group (`Аналитика`, `Продажи`, `Прогноз продаж`, `Бонусы`, `Справочники`, `Сервис`, `Администрирование`). Pick a Lucide icon that matches the screen's purpose.

```ts
{
  label: 'Аналитика',
  items: [
    { path: '/ai-recommendations', label: 'Рекомендации ИИ', icon: Sparkles, section: 'ai.recommendations' },
    { path: '/ai-diagnostics', label: 'Диагностика', icon: Activity, section: 'ai.diagnostics' },
  ],
},
```

CmdK and Topbar breadcrumbs both pull from `navSections`, so adding the entry here makes the page searchable and gives it a breadcrumb automatically.

## 7. Default role permissions (optional)

If the new section should be available to non-admin roles by default, update the seed in `app/auth_ui.py::seed_default_roles()`. Existing roles stay unchanged — only freshly seeded environments pick this up. For existing prod, an admin updates the role through the `/roles` UI.

Section key naming convention seen in existing roles:
- `admin` — gets every section
- `manager` — operational sections (departments, employees, sales.*, forecast.*, sync, ai.*)
- `accountant` — finance-related (departments, employees, sales.daily, sales.waiters, bonus.*)
- `viewer` — read-only sales/forecast subset

## 8. Build sanity check

```bash
cd frontend && pnpm build
```

If `tsc` fails on missing `SectionKey` literal, you forgot step 1. If the route compiles but the page doesn't appear in the sidebar, you forgot step 6. If the page 401s on load, you forgot to grant the section to your user's role.

## 9. Test

- Open the page directly via URL (verify ProtectedRoute lets you in).
- Open via sidebar click.
- Search for it via ⌘K.
- Toggle theme to dark — does it still look right?
- Switch accent (`document.documentElement.setAttribute('data-accent', 'indigo')` in DevTools) — does it survive?

## Common mistakes

- **Adding the route but forgetting `SectionKey`** — TypeScript fails: `Argument of type '"ai.diagnostics"' is not assignable to parameter of type 'SectionKey'`.
- **Adding `SectionKey` to types only, not to backend `AVAILABLE_SECTIONS`** — admin can't grant the section through the UI; role-update API rejects unknown sections.
- **Adding it to sidebar but not as a `<ProtectedRoute section="...">`** — page appears in nav for everyone, including users who shouldn't see it.
- **Hard-coding the section in `<ProtectedRoute>` as a string literal** — works but bypasses TypeScript exhaustiveness. Use the typed `SectionKey` value.
- **Using shadcn's pill `<Tabs>` instead of underline `.tabs`** — visual mismatch with Bonuses page. Match existing style.
