import { useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { useRoles, useUpdateRole } from '@/hooks/use-roles'
import type { AppRole, SectionKey } from '@/types/auth'

const SECTION_LABELS: Record<SectionKey, string> = {
  'dashboard': 'Дашборд',
  'departments': 'Подразделения',
  'employees': 'Сотрудники',
  'sales.daily': 'Продажи по дням',
  'sales.hourly': 'Продажи по часам',
  'sales.waiters': 'Продажи по официантам',
  'forecast.branches': 'Прогноз по филиалам',
  'forecast.comparison': 'Сравнение факт / прогноз',
  'forecast.sku': 'Прогноз по блюдам',
  'menu.products': 'Меню — товары',
  'menu.groups': 'Меню — группы',
  'receipts.list': 'Чеки — журнал',
  'receipts.stats': 'Чеки — по блюдам',
  'ai.recommendations': 'Рекомендации ИИ',
  'sync': 'Синхронизация данных',
  'users': 'Управление пользователями',
  'roles': 'Управление ролями',
}

interface DraftState {
  name: string
  sections: Set<SectionKey>
}

export function RolesPage() {
  const rolesQuery = useRoles()
  const updateMutation = useUpdateRole()
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({})
  const [savingCode, setSavingCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [savedCode, setSavedCode] = useState<string | null>(null)

  // Initialize drafts from server data
  useEffect(() => {
    if (!rolesQuery.data) return
    setDrafts((prev) => {
      const next = { ...prev }
      for (const r of rolesQuery.data!.roles) {
        if (!next[r.code]) {
          next[r.code] = {
            name: r.name,
            sections: new Set(r.allowed_sections),
          }
        }
      }
      return next
    })
  }, [rolesQuery.data])

  const availableSections = rolesQuery.data?.available_sections ?? []
  const roles = rolesQuery.data?.roles ?? []

  function toggleSection(code: string, section: SectionKey) {
    setDrafts((prev) => {
      const draft = prev[code] ?? { name: '', sections: new Set<SectionKey>() }
      const next = new Set(draft.sections)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return { ...prev, [code]: { ...draft, sections: next } }
    })
  }

  function setName(code: string, name: string) {
    setDrafts((prev) => {
      const draft = prev[code] ?? { name: '', sections: new Set<SectionKey>() }
      return { ...prev, [code]: { ...draft, name } }
    })
  }

  function isDirty(role: AppRole): boolean {
    const draft = drafts[role.code]
    if (!draft) return false
    if (draft.name !== role.name) return true
    if (draft.sections.size !== role.allowed_sections.length) return true
    for (const s of role.allowed_sections) if (!draft.sections.has(s)) return true
    return false
  }

  async function handleSave(role: AppRole) {
    const draft = drafts[role.code]
    if (!draft) return
    setError(null)
    setSavedCode(null)
    setSavingCode(role.code)
    try {
      await updateMutation.mutateAsync({
        code: role.code,
        name: role.is_system ? undefined : draft.name,
        allowed_sections: Array.from(draft.sections),
      })
      setSavedCode(role.code)
    } catch (err) {
      setError((err as { detail?: string })?.detail ?? 'Ошибка сохранения')
    } finally {
      setSavingCode(null)
    }
  }

  function handleReset(role: AppRole) {
    setDrafts((prev) => ({
      ...prev,
      [role.code]: { name: role.name, sections: new Set(role.allowed_sections) },
    }))
  }

  const orderedSections = useMemo(
    () => availableSections.slice().sort((a, b) => a.localeCompare(b)),
    [availableSections],
  )

  if (rolesQuery.isLoading) return <LoadingSpinner />

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Роли и доступы</h1>
        <p className="text-sm text-muted-foreground">
          Отмечайте, какие разделы должны быть видны пользователям с каждой ролью. Изменения применятся при следующем входе пользователя.
        </p>
      </div>

      {error && <ErrorAlert message={error} />}

      {roles.map((role) => {
        const draft = drafts[role.code] ?? { name: role.name, sections: new Set(role.allowed_sections) }
        const dirty = isDirty(role)
        return (
          <Card key={role.code}>
            <CardHeader className="flex flex-row items-start justify-between space-y-0">
              <div className="space-y-1">
                <CardTitle className="flex items-center gap-2">
                  {role.is_system ? role.name : (
                    <Input
                      className="max-w-sm"
                      value={draft.name}
                      onChange={(e) => setName(role.code, e.target.value)}
                    />
                  )}
                  {role.is_system && <Badge variant="secondary">системная</Badge>}
                </CardTitle>
                <CardDescription className="font-mono text-xs">{role.code}</CardDescription>
              </div>
              <div className="flex gap-2">
                {savedCode === role.code && !dirty && (
                  <Badge>сохранено</Badge>
                )}
                <Button variant="outline" disabled={!dirty} onClick={() => handleReset(role)}>
                  Сбросить
                </Button>
                <Button
                  disabled={!dirty || savingCode === role.code}
                  onClick={() => void handleSave(role)}
                >
                  {savingCode === role.code ? 'Сохраняем...' : 'Сохранить'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                Доступные разделы
              </Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-2">
                {orderedSections.map((section) => {
                  const checked = draft.sections.has(section)
                  return (
                    <label
                      key={section}
                      className="flex items-center gap-2 rounded-md border px-3 py-2 hover:bg-muted cursor-pointer text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSection(role.code, section)}
                      />
                      <span className="flex-1">{SECTION_LABELS[section] ?? section}</span>
                      <span className="text-xs text-muted-foreground font-mono">{section}</span>
                    </label>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
