import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function ForbiddenPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Доступ запрещён</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            У вашей роли нет прав на этот раздел. Обратитесь к администратору, если считаете это ошибкой.
          </p>
          <Button asChild>
            <Link to="/">На главную</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
