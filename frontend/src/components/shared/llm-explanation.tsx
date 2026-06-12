import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useExplainRecommendation } from '@/hooks/use-pricing'
import { formatCurrency } from '@/lib/formatters'
import type { PriceRecommendation } from '@/types/pricing'

/** C4': структурированное LLM-обоснование рекомендации цены (ТЗ п.4.8). */
interface StructuredExplanation {
  summary?: string
  factors?: string[]
  expected_effect?: {
    delta_gp_weekly?: number | null
    delta_qty_pct?: number | null
    price_change?: string | null
  }
  risks?: string[]
  recommended_action?: string
}

function parseExplanation(raw: string | null | undefined): StructuredExplanation | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const obj = JSON.parse(trimmed) as StructuredExplanation
    return obj && typeof obj === 'object' && obj.summary ? obj : null
  } catch {
    return null
  }
}

function fmtPctSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

export function LlmExplanation({ rec }: { rec: PriceRecommendation }) {
  const explainMut = useExplainRecommendation()
  const structured = parseExplanation(rec.llm_explanation)

  if (!rec.llm_explanation) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">Обоснование ещё не сгенерировано.</p>
        <Button
          size="sm"
          variant="outline"
          onClick={() => explainMut.mutate({ id: rec.id })}
          disabled={explainMut.isPending}
        >
          <Sparkles className={`h-3.5 w-3.5 mr-1.5 ${explainMut.isPending ? 'animate-pulse' : ''}`} />
          {explainMut.isPending ? 'Генерация… (5–15 с)' : 'Сгенерировать обоснование'}
        </Button>
        {explainMut.error && (
          <p className="text-xs" style={{ color: 'var(--neg)' }}>
            Не удалось сгенерировать: {explainMut.error.message}
          </p>
        )}
      </div>
    )
  }

  if (!structured) {
    return <p className="text-sm whitespace-pre-wrap">{rec.llm_explanation}</p>
  }

  return (
    <div className="space-y-2 text-sm">
      <p>{structured.summary}</p>
      {structured.factors && structured.factors.length > 0 && (
        <ul className="space-y-0.5">
          {structured.factors.map((f, i) => (
            <li key={i} className="flex gap-1.5">
              <span style={{ color: 'var(--accent)' }}>•</span>
              <span>{f}</span>
            </li>
          ))}
        </ul>
      )}
      {structured.expected_effect && (
        <div className="text-xs text-muted-foreground">
          Ожидаемый эффект:{' '}
          <span className="tabular" style={{ color: 'var(--text)' }}>
            {structured.expected_effect.price_change ?? ''}
            {structured.expected_effect.delta_gp_weekly != null &&
              ` · ΔGP ${formatCurrency(structured.expected_effect.delta_gp_weekly)}/нед`}
            {structured.expected_effect.delta_qty_pct != null &&
              ` · спрос ${fmtPctSigned(structured.expected_effect.delta_qty_pct)}`}
          </span>
        </div>
      )}
      {structured.risks && structured.risks.length > 0 && (
        <ul className="space-y-0.5">
          {structured.risks.map((r, i) => (
            <li key={i} className="flex gap-1.5 text-xs" style={{ color: 'var(--warn)' }}>
              <span>⚠</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
      {structured.recommended_action && (
        <p className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
          {structured.recommended_action}
        </p>
      )}
    </div>
  )
}
