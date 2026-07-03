export type AIProvider = 'claude' | 'openai' | 'openrouter' | 'gemini'

export interface AIProviderInfo {
  provider: AIProvider
  configured: boolean
  model?: string
  status?: string
  isolated_keys?: Record<string, boolean>
}

export interface AIProvidersResponse {
  supported_providers: AIProvider[]
  default_provider: AIProvider
  providers: Record<AIProvider, AIProviderInfo>
}

export interface AIPromptInfo {
  agent_name: string
  prompt: string
  source: 'db' | 'default'
  updated_at: string | null
}

export interface AIHistoryItem {
  id: number
  department_id: string
  department_name: string | null
  date_start: string
  date_end: string
  provider: AIProvider
  agent_count: number
  created_at: string
}

export interface AIAnalyzeRequest {
  department_id: string
  date_start: string
  date_end: string
  provider: AIProvider
}

export interface AIAnalyzeResponse {
  analysis_id: number
  department_id: string
  date_start: string
  date_end: string
  provider: AIProvider
  success: boolean
  results: Record<string, string>
  errors: Record<string, string>
  skipped: string[]
  metadata: Record<string, unknown>
  created_at: string
}

export interface AIPromptLog {
  full_prompt: string
  system_prompt: string | null
  provider: AIProvider
  success: boolean
  tokens_used: number
  request_timestamp: string
  response_timestamp: string | null
  response_time_seconds: number | null
  error_message: string | null
}

export interface AIAgentDetail {
  agent_name: string
  title: string
  enabled: boolean
  result: string | null
  has_result: boolean
  prompt: AIPromptLog | null
}

export interface AIAnalysisDetail {
  id: number
  department_id: string
  department_name: string | null
  date_start: string
  date_end: string
  provider: AIProvider
  agent_results: Record<string, string>
  created_at: string
}

export interface AIAnalysisPromptsResponse {
  analysis: AIAnalysisDetail
  agents: AIAgentDetail[]
}

export interface AIRerunAgentRequest {
  analysis_id: number
  agent_name: string
  new_prompt?: string
  provider: AIProvider
}

export interface AIRerunAgentResponse {
  success: boolean
  agent_name: string
  result: string | null
  error: string | null
  tokens_used: number
}
