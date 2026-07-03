declare global {
  interface Window {
    __API_TOKEN__?: string
  }
}

const SESSION_STORAGE_KEY = 'sf.session_token'

function getApiToken(): string {
  if (typeof window !== 'undefined' && window.__API_TOKEN__) {
    return window.__API_TOKEN__
  }
  return (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_TOKEN || ''
}

export function getSessionToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(SESSION_STORAGE_KEY)
}

export function setSessionToken(token: string | null) {
  if (typeof window === 'undefined') return
  if (token) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, token)
  } else {
    window.localStorage.removeItem(SESSION_STORAGE_KEY)
  }
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(response: Response, detail?: string) {
    super(`API Error: ${response.status}`)
    this.status = response.status
    this.detail = detail || response.statusText
  }
}

/** Человекочитаемый текст ошибки: detail бека (напр. 409 max_changes_per_cycle) или message. */
export function apiErrorMessage(err: unknown): string {
  const detail = (err as { detail?: string })?.detail
  if (detail) return detail
  return err instanceof Error ? err.message : String(err)
}

type SessionExpiredHandler = () => void
let sessionExpiredHandler: SessionExpiredHandler | null = null

export function setSessionExpiredHandler(fn: SessionExpiredHandler | null) {
  sessionExpiredHandler = fn
}

class ApiClient {
  private getHeaders(json = true): HeadersInit {
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${getApiToken()}`,
    }
    const sessionToken = getSessionToken()
    if (sessionToken) {
      headers['X-Session-Token'] = sessionToken
    }
    if (json) {
      headers['Content-Type'] = 'application/json'
    }
    return headers
  }

  private handleAuthFailure(response: Response, body: { detail?: string }): never {
    // Treat 401 with a session token present as an expired session
    if (response.status === 401 && getSessionToken()) {
      setSessionToken(null)
      sessionExpiredHandler?.()
    }
    throw new ApiError(response, body.detail || response.statusText)
  }

  async get<T>(url: string, params?: Record<string, string | undefined>): Promise<T> {
    const filteredParams: Record<string, string> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== '') filteredParams[k] = v
      }
    }
    const searchParams = Object.keys(filteredParams).length
      ? '?' + new URLSearchParams(filteredParams).toString()
      : ''
    const response = await fetch(`${url}${searchParams}`, {
      headers: this.getHeaders(false),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      this.handleAuthFailure(response, body)
    }
    return response.json()
  }

  async post<T>(url: string, body?: unknown, params?: Record<string, string | undefined>): Promise<T> {
    const filteredParams: Record<string, string> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== '') filteredParams[k] = v
      }
    }
    const searchParams = Object.keys(filteredParams).length
      ? '?' + new URLSearchParams(filteredParams).toString()
      : ''
    const response = await fetch(`${url}${searchParams}`, {
      method: 'POST',
      headers: this.getHeaders(body !== undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) {
      const respBody = await response.json().catch(() => ({}))
      this.handleAuthFailure(response, respBody)
    }
    return response.json()
  }

  async put<T>(url: string, body: unknown): Promise<T> {
    const response = await fetch(url, {
      method: 'PUT',
      headers: this.getHeaders(),
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      const respBody = await response.json().catch(() => ({}))
      this.handleAuthFailure(response, respBody)
    }
    return response.json()
  }

  async delete<T>(url: string): Promise<T> {
    const response = await fetch(url, {
      method: 'DELETE',
      headers: this.getHeaders(false),
    })
    if (!response.ok) {
      const respBody = await response.json().catch(() => ({}))
      this.handleAuthFailure(response, respBody)
    }
    return response.json()
  }
}

export const api = new ApiClient()

/** Fetch a binary file (e.g. XLSX export) with auth headers and return a Blob. */
export async function apiDownload(url: string): Promise<Blob> {
  const headers: Record<string, string> = {
    'Authorization': `Bearer ${getApiToken()}`,
  }
  const sessionToken = getSessionToken()
  if (sessionToken) headers['X-Session-Token'] = sessionToken
  const response = await fetch(url, { headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response, (body as { detail?: string }).detail)
  }
  return response.blob()
}
