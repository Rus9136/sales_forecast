import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  className?: string
  text?: string
}

export function LoadingSpinner({ className, text = 'Загрузка данных...' }: LoadingSpinnerProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 text-muted-foreground', className)}>
      <Loader2 className="h-8 w-8 animate-spin mb-3" />
      <p className="text-sm">{text}</p>
    </div>
  )
}
