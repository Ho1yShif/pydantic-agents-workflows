import type { AnswerResponse, ProgressUpdate } from '../types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const POLL_INTERVAL_MS = 1500

const CLIENT_ID_KEY = 'client_id'

/**
 * Stable anonymous identifier for this browser, used to scope Q&A history to
 * the current user (the app has no auth). Generated once and persisted in
 * localStorage; resets if the user clears storage or switches devices.
 */
export function getClientId(): string {
  // SSR / non-browser: no stable storage, so return a throwaway id.
  if (typeof window === 'undefined') return 'ssr'

  let clientId = window.localStorage.getItem(CLIENT_ID_KEY)
  if (!clientId) {
    clientId = crypto.randomUUID()
    window.localStorage.setItem(CLIENT_ID_KEY, clientId)
  }
  return clientId
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true }
    )
  })
}

/**
 * Ask a question via the in-process pipeline.
 *
 * POST /ask starts the pipeline as a background task and returns a run id; we
 * poll GET /ask/{run_id} for the result. The pipeline runs out-of-band from the
 * polling request, so token-by-token answer streaming is unavailable
 * (`onAnswerToken` is unused). The orchestrator records real per-stage progress
 * under a token, which we poll alongside the run status and replay through
 * `onProgress` as each new stage lands.
 */
export async function askQuestion(
  question: string,
  onProgress?: (update: ProgressUpdate) => void,
  _onAnswerToken?: (delta: string) => void,
  signal?: AbortSignal
): Promise<AnswerResponse> {
  // 1. Start the pipeline run.
  const startResponse = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, client_id: getClientId() }),
    signal,
  })

  if (!startResponse.ok) {
    throw new Error(`API error: ${startResponse.statusText}`)
  }

  const { run_id: runId, progress_token: progressToken } = (await startResponse.json()) as {
    run_id: string
    progress_token?: string
  }

  const progressQuery = progressToken ? `?progress_token=${encodeURIComponent(progressToken)}` : ''

  // 2. Poll for completion. The server returns the cumulative list of stage
  //    updates each time; replay only the ones we haven't surfaced yet.
  let seen = 0
  const replayNew = (updates?: ProgressUpdate[]) => {
    if (!updates || !onProgress) return
    for (; seen < updates.length; seen++) {
      onProgress(updates[seen])
    }
  }

  while (true) {
    await delay(POLL_INTERVAL_MS, signal)

    const pollResponse = await fetch(`${API_BASE_URL}/ask/${runId}${progressQuery}`, { signal })
    if (!pollResponse.ok) {
      throw new Error(`API error: ${pollResponse.statusText}`)
    }

    const data = (await pollResponse.json()) as {
      status: 'running' | 'done' | 'failed'
      result?: AnswerResponse
      error?: string
      updates?: ProgressUpdate[]
    }

    replayNew(data.updates)

    if (data.status === 'done' && data.result) {
      return data.result
    }

    if (data.status === 'failed') {
      throw new Error(data.error || 'Pipeline run failed')
    }
  }
}

export async function checkHealth(): Promise<{ status: string; database_connected: boolean }> {
  const response = await fetch(`${API_BASE_URL}/health`)
  
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`)
  }

  return response.json()
}

export interface HistorySession {
  id: string
  question: string
  answer: string
  sources: any[]
  claims: any[]
  evaluations: any[]
  quality_score: number
  total_cost: number
  total_duration_ms: number
  created_at: string
  stages?: any[]  // Pipeline stages (optional for backwards compatibility)
  trace_id?: string  // Logfire trace ID (optional)
}

export async function getHistory(limit: number = 20): Promise<HistorySession[]> {
  const response = await fetch(
    `${API_BASE_URL}/history?limit=${limit}&client_id=${encodeURIComponent(getClientId())}`
  )
  
  if (!response.ok) {
    throw new Error(`Failed to fetch history: ${response.statusText}`)
  }

  const data = await response.json()
  return data.sessions
}

export async function getSession(sessionId: string): Promise<HistorySession> {
  const response = await fetch(
    `${API_BASE_URL}/history/${sessionId}?client_id=${encodeURIComponent(getClientId())}`
  )
  
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`)
  }

  return response.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/history/${sessionId}?client_id=${encodeURIComponent(getClientId())}`,
    {
      method: 'DELETE',
    }
  )
  
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.statusText}`)
  }
}

export async function clearAllHistory(): Promise<{ count: number }> {
  const response = await fetch(
    `${API_BASE_URL}/history?client_id=${encodeURIComponent(getClientId())}`,
    {
      method: 'DELETE',
    }
  )
  
  if (!response.ok) {
    throw new Error(`Failed to clear history: ${response.statusText}`)
  }

  return response.json()
}

export interface LogfireLog {
  timestamp: string
  message: string
  level: string
  span_name: string
  attributes: Record<string, any>
  service_name: string
}

export interface SessionLogsResponse {
  trace_id: string
  logs: LogfireLog[]
  columns: string[]
}

export async function getSessionLogs(sessionId: string): Promise<SessionLogsResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/logs`)
  
  if (!response.ok) {
    if (response.status === 404) {
      const error = await response.json()
      throw new Error(error.detail || 'Logs not found')
    }
    if (response.status === 501) {
      throw new Error('Logfire integration not configured')
    }
    throw new Error('Failed to fetch logs')
  }
  
  return response.json()
}

