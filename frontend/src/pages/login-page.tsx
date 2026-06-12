import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { PhoneInput } from '@/components/ui/phone-input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAuth } from '@/contexts/auth-context'
import { isPhoneComplete, toBackendPhone } from '@/lib/phone'

export function LoginPage() {
  const { login, status, error: ctxError } = useAuth()
  const [digits, setDigits] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const location = useLocation() as { state?: { from?: string } }

  if (status === 'authenticated') {
    return <Navigate to={location.state?.from || '/'} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!isPhoneComplete(digits)) {
      setLocalError('Введите полный номер телефона')
      return
    }
    setLocalError(null)
    setSubmitting(true)
    try {
      await login(toBackendPhone(digits))
    } catch (err) {
      setLocalError((err as { detail?: string })?.detail || 'Не удалось войти')
    } finally {
      setSubmitting(false)
    }
  }

  const errorMessage = localError || ctxError

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted px-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader>
          <CardTitle>Вход в Sales Forecast</CardTitle>
          <CardDescription>
            Введите номер телефона, привязанный к учётной записи.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Номер телефона</Label>
              <PhoneInput
                id="phone"
                value={digits}
                onChange={setDigits}
                autoFocus
                required
              />
            </div>
            {errorMessage && (
              <Alert variant="destructive">
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            )}
            <Button
              type="submit"
              className="w-full"
              disabled={submitting || !isPhoneComplete(digits)}
            >
              {submitting ? 'Входим...' : 'Войти'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
