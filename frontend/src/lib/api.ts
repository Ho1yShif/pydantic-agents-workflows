import type { AnswerResponse, ProgressUpdate } from '../types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const POLL_INTERVAL_MS = 1500

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
 * Ask a question via the Workflows-backed pipeline.
 *
 * The gateway triggers a Render Workflow run and we poll it for the result.
 * Token-by-token streaming is no longer available (the pipeline runs
 * out-of-band in the Workflow service), so `onAnswerToken` is unused and
 * `onProgress` receives coarse status updates while the run is in flight.
 */
export async function askQuestion(
  question: string,
  onProgress?: (update: ProgressUpdate) => void,
  _onAnswerToken?: (delta: string) => void,
  signal?: AbortSignal
): Promise<AnswerResponse> {
  // 1. Trigger the workflow run.
  const startResponse = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })

  if (!startResponse.ok) {
    throw new Error(`API error: ${startResponse.statusText}`)
  }

  const { run_id: runId } = (await startResponse.json()) as { run_id: string }

  onProgress?.({
    stage: 'pipeline',
    status: 'started',
    message: 'Running the answer pipeline…',
    progress: 10,
    cost_so_far: 0,
  })

  // 2. Poll for completion.
  let polls = 0
  while (true) {
    await delay(POLL_INTERVAL_MS, signal)

    const pollResponse = await fetch(`${API_BASE_URL}/ask/${runId}`, { signal })
    if (!pollResponse.ok) {
      throw new Error(`API error: ${pollResponse.statusText}`)
    }

    const data = (await pollResponse.json()) as {
      status: 'running' | 'done' | 'failed'
      result?: AnswerResponse
      error?: string
    }

    if (data.status === 'done' && data.result) {
      onProgress?.({
        stage: 'pipeline',
        status: 'completed',
        message: 'Answer ready',
        progress: 100,
        cost_so_far: data.result.total_cost ?? 0,
      })
      return data.result
    }

    if (data.status === 'failed') {
      throw new Error(data.error || 'Pipeline run failed')
    }

    // Still running — nudge the progress bar toward (but never reaching) 90%.
    polls += 1
    onProgress?.({
      stage: 'pipeline',
      status: 'started',
      message: 'Running the answer pipeline…',
      progress: Math.min(10 + polls * 8, 90),
      cost_so_far: 0,
    })
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
  iterations: number
  total_cost: number
  total_duration_ms: number
  created_at: string
  stages?: any[]  // Pipeline stages (optional for backwards compatibility)
  trace_id?: string  // Logfire trace ID (optional)
}

export async function getHistory(limit: number = 20): Promise<HistorySession[]> {
  const response = await fetch(`${API_BASE_URL}/history?limit=${limit}`)
  
  if (!response.ok) {
    throw new Error(`Failed to fetch history: ${response.statusText}`)
  }

  const data = await response.json()
  return data.sessions
}

export async function getSession(sessionId: string): Promise<HistorySession> {
  const response = await fetch(`${API_BASE_URL}/history/${sessionId}`)
  
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`)
  }

  return response.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/history/${sessionId}`, {
    method: 'DELETE',
  })
  
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.statusText}`)
  }
}

export async function clearAllHistory(): Promise<{ count: number }> {
  const response = await fetch(`${API_BASE_URL}/history`, {
    method: 'DELETE',
  })
  
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

