import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type {
  AIAnalysisPromptsResponse,
  AIAnalyzeRequest,
  AIAnalyzeResponse,
  AIHistoryItem,
  AIPromptInfo,
  AIProvidersResponse,
  AIRerunAgentRequest,
  AIRerunAgentResponse,
} from '@/types/ai'

const BASE = '/api/ai-recommendations'

export function useAIProviders() {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => api.get<AIProvidersResponse>(`${BASE}/providers`),
    staleTime: 5 * 60_000,
  })
}

export function useAIPrompts() {
  return useQuery({
    queryKey: ['ai-prompts'],
    queryFn: () => api.get<AIPromptInfo[]>(`${BASE}/prompts`),
  })
}

export function useUpdateAIPrompts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (prompts: Record<string, string>) =>
      api.put<{ updated: string[]; count: number }>(`${BASE}/prompts`, { prompts }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-prompts'] })
    },
  })
}

export function useAIHistory(params?: { department_id?: string; limit?: number }) {
  return useQuery({
    queryKey: ['ai-history', params],
    queryFn: () =>
      api.get<AIHistoryItem[]>(`${BASE}/history`, {
        department_id: params?.department_id,
        limit: params?.limit ? String(params.limit) : '20',
      }),
  })
}

export function useAIAnalysisPrompts(analysisId: number | null) {
  return useQuery({
    queryKey: ['ai-analysis-prompts', analysisId],
    queryFn: () => api.get<AIAnalysisPromptsResponse>(`${BASE}/prompts/${analysisId}`),
    enabled: analysisId != null,
  })
}

export function useRunAIAnalysis() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AIAnalyzeRequest) =>
      api.post<AIAnalyzeResponse>(`${BASE}/analyze`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-history'] })
    },
  })
}

export function useRerunAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AIRerunAgentRequest) =>
      api.post<AIRerunAgentResponse>(`${BASE}/rerun-agent`, payload),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['ai-analysis-prompts', variables.analysis_id] })
      qc.invalidateQueries({ queryKey: ['ai-history'] })
    },
  })
}
