import { Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  className?: string
  text?: string
}

export function EmptyState({ className, text = 'Нет данных для отображения' }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 text-muted-foreground', className)}>
      <Inbox className="h-12 w-12 mb-3 opacity-30" />
      <p className="text-sm">{text}</p>
    </div>
  )
}
