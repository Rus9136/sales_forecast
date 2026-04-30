import { useState, type FormEvent } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { ErrorAlert } from '@/components/shared/error-alert'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { useAuth } from '@/contexts/auth-context'
import { useRoles } from '@/hooks/use-roles'
import {
  useCreateUser,
  useDeleteUser,
  useUpdateUser,
  useUsers,
} from '@/hooks/use-users'
import type { AppUser } from '@/types/auth'

interface FormState {
  phone: string
  full_name: string
  role_code: string
  is_active: boolean
}

const emptyForm: FormState = {
  phone: '',
  full_name: '',
  role_code: 'viewer',
  is_active: true,
}

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const usersQuery = useUsers()
  const rolesQuery = useRoles()
  const createMutation = useCreateUser()
  const updateMutation = useUpdateUser()
  const deleteMutation = useDeleteUser()

  const [editing, setEditing] = useState<AppUser | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [confirmDelete, setConfirmDelete] = useState<AppUser | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  function openCreate() {
    setForm(emptyForm)
    setFormError(null)
    setCreating(true)
  }

  function openEdit(u: AppUser) {
    setForm({
      phone: u.phone,
      full_name: u.full_name ?? '',
      role_code: u.role_code,
      is_active: u.is_active,
    })
    setFormError(null)
    setEditing(u)
  }

  function closeModal() {
    setCreating(false)
    setEditing(null)
    setFormError(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    try {
      if (editing) {
        await updateMutation.mutateAsync({
          id: editing.id,
          data: {
            phone: form.phone,
            full_name: form.full_name || null,
            role_code: form.role_code,
            is_active: form.is_active,
          },
        })
      } else {
        await createMutation.mutateAsync({
          phone: form.phone,
          full_name: form.full_name || null,
          role_code: form.role_code,
          is_active: form.is_active,
        })
      }
      closeModal()
    } catch (err) {
      setFormError((err as { detail?: string })?.detail ?? 'Ошибка сохранения')
    }
  }

  async function handleDelete(u: AppUser) {
    try {
      await deleteMutation.mutateAsync(u.id)
      setConfirmDelete(null)
    } catch (err) {
      setFormError((err as { detail?: string })?.detail ?? 'Ошибка удаления')
    }
  }

  const roles = rolesQuery.data?.roles ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Пользователи</h1>
          <p className="text-sm text-muted-foreground">
            Создавайте учётные записи и назначайте роли — раздел доступен только администраторам.
          </p>
        </div>
        <Button onClick={openCreate}>+ Новый пользователь</Button>
      </div>

      {usersQuery.error && <ErrorAlert message={(usersQuery.error as Error).message} />}

      <Card>
        <CardContent className="p-0">
          {usersQuery.isLoading ? (
            <LoadingSpinner />
          ) : !usersQuery.data || usersQuery.data.length === 0 ? (
            <EmptyState text="Нет пользователей" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ФИО</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead>Роль</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Последний вход</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usersQuery.data.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">
                      {u.full_name || '—'}
                      {currentUser?.id === u.id && (
                        <Badge variant="secondary" className="ml-2">вы</Badge>
                      )}
                    </TableCell>
                    <TableCell>{u.phone}</TableCell>
                    <TableCell>{u.role_name || u.role_code}</TableCell>
                    <TableCell>
                      {u.is_active ? (
                        <Badge>активен</Badge>
                      ) : (
                        <Badge variant="secondary">отключён</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString('ru-RU') : '—'}
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      <Button variant="outline" size="sm" onClick={() => openEdit(u)}>
                        Изменить
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={currentUser?.id === u.id}
                        onClick={() => setConfirmDelete(u)}
                      >
                        Удалить
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={creating || editing !== null} onOpenChange={(o) => { if (!o) closeModal() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Изменить пользователя' : 'Новый пользователь'}</DialogTitle>
            <DialogDescription>
              Авторизация выполняется по номеру телефона. Доступ к разделам определяет роль.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Телефон</Label>
              <Input
                id="phone"
                type="tel"
                placeholder="+7 (700) 123-45-67"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="full_name">ФИО</Label>
              <Input
                id="full_name"
                value={form.full_name}
                onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Роль</Label>
              <Select
                value={form.role_code}
                onValueChange={(v) => setForm((f) => ({ ...f, role_code: v }))}
              >
                <SelectTrigger id="role">
                  <SelectValue placeholder="Выберите роль" />
                </SelectTrigger>
                <SelectContent>
                  {roles.map((r) => (
                    <SelectItem key={r.code} value={r.code}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              Активен
            </label>

            {formError && <ErrorAlert message={formError} />}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={closeModal}>Отмена</Button>
              <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                {editing ? 'Сохранить' : 'Создать'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete !== null}
        onOpenChange={(o) => { if (!o) setConfirmDelete(null) }}
        title="Удалить пользователя?"
        description={`Учётная запись ${confirmDelete?.full_name || confirmDelete?.phone || ''} будет удалена. Это действие нельзя отменить.`}
        onConfirm={() => { if (confirmDelete) void handleDelete(confirmDelete) }}
        destructive
        confirmText="Удалить"
      />
    </div>
  )
}
