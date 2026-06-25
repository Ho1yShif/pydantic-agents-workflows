export interface Document {
  content: string
  source: string
  similarity_score: number
  metadata: Record<string, any>
}

export interface Claim {
  claim: string
  verified: boolean
  verification_score: number
  supporting_docs: string[]
}

export interface EvaluationResult {
  model: string
  score: number
  technical_accuracy: number
  clarity: number
  completeness: number
  developer_value: number
  feedback: string
}

export interface PipelineStageResult {
  stage: string
  success: boolean
  duration_ms: number
  cost_usd: number
  tokens_used?: number
  model?: string
  error?: string
  metadata?: Record<string, any>
}

export interface AnswerResponse {
  question: string
  answer: string
  sources: Document[]
  claims: Claim[]
  quality_score: number
  accuracy_score?: number
  evaluations: EvaluationResult[]
  iterations: number
  total_cost: number
  total_duration_ms: number
  stages: PipelineStageResult[]
  timestamp: string
  session_id?: string
}

export interface ProgressUpdate {
  stage: string
  status: 'started' | 'completed' | 'failed'
  message: string
  progress: number
  cost_so_far: number
  duration_ms?: number
}

