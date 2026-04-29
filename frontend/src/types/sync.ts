export interface AutoSyncLog {
  id: number
  sync_date: string
  sync_type: string
  status: string
  message: string
  summary_records: number
  hourly_records: number
  total_raw_records: number
  error_details: string | null
  executed_at: string
  created_at: string
}

export interface SyncStatistics {
  total_logs: number
  success_count_30d: number
  error_count_30d: number
  success_rate_30d: number
  latest_success: {
    date: string
    executed_at: string
    message: string
    records: number
  } | null
  latest_error: {
    date: string
    executed_at: string
    message: string
    error_details: string | null
  } | null
}

export interface SyncStatusResponse {
  logs: AutoSyncLog[]
  statistics: SyncStatistics
}
