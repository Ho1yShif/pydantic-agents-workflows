'use client'

import { useState } from 'react'
import { AnswerResponse } from '@/types'

interface MetricsPanelProps {
  answer: AnswerResponse
}

export default function MetricsPanel({ answer }: MetricsPanelProps) {
  const [showDetails, setShowDetails] = useState(false)
  const [showCostBreakdown, setShowCostBreakdown] = useState(false)

  // Debug: Log answer structure
  console.log('MetricsPanel received answer:', {
    has_stages: !!answer.stages,
    stages_length: answer.stages?.length || 0,
    stages: answer.stages
  })

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms.toFixed(0)}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const formatCost = (usd: number) => {
    return `$${usd.toFixed(4)}`
  }

  // Calculate overall confidence score
  const verifiedCount = answer.claims.filter(c => c.verified).length
  const verificationRate = answer.claims.length > 0 
    ? (verifiedCount / answer.claims.length) * 100 
    : 0
  
  const confidenceScore = Math.round(
    (answer.quality_score * 0.5) + (verificationRate * 0.5)
  )

  const getConfidenceColor = (score: number) => {
    if (score >= 80) return { bg: 'bg-green-500/10', border: 'border-green-500/50', text: 'text-green-400', dot: 'bg-green-500' }
    if (score >= 60) return { bg: 'bg-yellow-500/10', border: 'border-yellow-500/50', text: 'text-yellow-400', dot: 'bg-yellow-500' }
    return { bg: 'bg-red-500/10', border: 'border-red-500/50', text: 'text-red-400', dot: 'bg-red-500' }
  }

  const getConfidenceLabel = (score: number) => {
    if (score >= 80) return 'High confidence'
    if (score >= 60) return 'Moderate confidence'
    return 'Low confidence'
  }

  const colors = getConfidenceColor(confidenceScore)

  return (
    <div className="space-y-6">
      {/* Confidence score Card */}
      <div className="bg-black border border-zinc-800 p-6 hover:border-zinc-700 transition-colors duration-200">
        <h3 className="text-lg font-semibold text-zinc-300 mb-4">Confidence score</h3>
        
        <div className={`${colors.bg} border ${colors.border} p-4 mb-4`}>
          <div className="flex items-center gap-3 mb-2">
            <div className={`w-3 h-3 rounded-full ${colors.dot}`}></div>
            <span className={`text-sm font-semibold ${colors.text} tracking-wide`}>
              {getConfidenceLabel(confidenceScore)}
            </span>
          </div>
          <div className={`text-3xl font-bold ${colors.text}`}>
            {confidenceScore}%
          </div>
          <p className="text-xs text-zinc-400 mt-2">
            Based on {verifiedCount}/{answer.claims.length} verified claims
          </p>
        </div>

        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full flex items-center justify-between text-sm text-zinc-400 hover:text-purple-400 transition-colors"
        >
          <span>{showDetails ? 'Hide' : 'Show'} detailed metrics</span>
          <svg 
            className={`w-4 h-4 transition-transform ${showDetails ? 'rotate-180' : ''}`}
            fill="none" 
            stroke="currentColor" 
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showDetails && (
          <div className="mt-4 pt-4 border-t border-zinc-800 space-y-4">
            {/* Quality Score */}
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-zinc-400">Quality Score</span>
                <span className="text-white font-medium">{answer.quality_score.toFixed(0)}/100</span>
              </div>
              <div className="w-full bg-zinc-900 h-2 border border-zinc-800">
                <div
                  className={`h-full transition-all duration-500 ${
                    answer.quality_score >= 85
                      ? 'bg-green-500'
                      : answer.quality_score >= 70
                      ? 'bg-yellow-500'
                      : 'bg-red-500'
                  }`}
                  style={{ width: `${answer.quality_score}%` }}
                />
              </div>
            </div>

            {/* Verification Rate */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-zinc-400">Verification Rate</span>
              <span className="text-sm text-white font-medium">
                {verificationRate.toFixed(0)}% ({verifiedCount}/{answer.claims.length})
              </span>
            </div>

            {/* Accuracy Score */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-zinc-400">Accuracy Score</span>
              <span className="text-sm text-white font-medium">
                {(answer.accuracy_score || 0).toFixed(0)}/100
              </span>
            </div>

            {/* Duration */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-zinc-400">Duration</span>
              <span className="text-sm text-white font-medium">
                {formatDuration(answer.total_duration_ms || 0)}
              </span>
            </div>

            {/* Cost */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-zinc-400">Total Cost</span>
              <span className="text-sm text-yellow-500 font-medium">
                {formatCost(answer.total_cost || 0)}
              </span>
            </div>

            {/* Documents */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-zinc-400">Documents Retrieved</span>
              <span className="text-sm text-white font-medium">
                {answer.sources.length}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Pipeline Cost breakdown Card */}
      <div className="bg-black border border-zinc-800 p-6 hover:border-zinc-700 transition-colors duration-200">
        <h3 className="text-lg font-semibold text-zinc-300 mb-4">Cost breakdown</h3>
        
        {/* Summary always visible */}
        <div className="mb-4">
          <div className="text-center py-4">
            <div className="text-3xl font-bold text-yellow-500 mb-2">
              {formatCost(answer.total_cost || 0)}
            </div>
            <p className="text-xs text-zinc-400">
              Total API cost
            </p>
          </div>
        </div>

        {/* Show expand button only if there are stages */}
        {answer.stages && answer.stages.length > 0 && (
          <>
            <button
              onClick={() => setShowCostBreakdown(!showCostBreakdown)}
              className="w-full flex items-center justify-between text-sm text-zinc-400 hover:text-purple-400 transition-colors"
            >
              <span>{showCostBreakdown ? 'Hide' : 'Show'} stage breakdown</span>
              <svg 
                className={`w-4 h-4 transition-transform ${showCostBreakdown ? 'rotate-180' : ''}`}
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {showCostBreakdown && (
              <div className="mt-4 pt-4 border-t border-zinc-800 space-y-2">
                {answer.stages.map((stage, idx) => (
                  <div
                    key={idx}
                    className="flex justify-between items-center text-sm py-2 border-b border-zinc-800 last:border-b-0"
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="text-zinc-400 capitalize">
                        {stage.stage.replace(/_/g, ' ')}
                      </span>
                      {stage.model && (
                        <span className="text-zinc-600 text-xs font-mono">
                          {stage.model}
                        </span>
                      )}
                    </div>
                    <span className="text-yellow-500 font-mono text-xs shrink-0 ml-2">
                      {formatCost(stage.cost_usd || 0)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Evaluations Card */}
      {answer.evaluations.length > 0 && (
        <div className="bg-black border border-zinc-800 p-6 hover:border-zinc-700 transition-colors duration-200">
          <h3 className="text-lg font-semibold text-zinc-300 mb-4">Evaluations</h3>

          {/* Average score */}
          <div className="text-center py-3 mb-4">
            <div className="text-3xl font-bold text-purple-600 mb-1">
              {Math.round(answer.evaluations.reduce((sum, e) => sum + e.score, 0) / answer.evaluations.length)}/100
            </div>
            <p className="text-xs text-zinc-400">
              Average across {answer.evaluations.length} evaluation{answer.evaluations.length > 1 ? 's' : ''}
            </p>
          </div>

          {/* Per-evaluation breakdown — always visible */}
          <div className="border-t border-zinc-800 pt-4 space-y-4">
            {answer.evaluations.map((evaluation, idx) => (
              <div key={idx} className="border-t border-zinc-800 pt-4 first:border-t-0 first:pt-0">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-sm font-medium text-zinc-300">
                    {evaluation.model.includes('gpt') ? 'OpenAI' : 'Anthropic'}
                  </span>
                  <span className="text-sm font-medium text-purple-600">
                    {evaluation.score}/100
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-400">Technical accuracy</span>
                    <span className="text-zinc-300">{evaluation.technical_accuracy}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-400">Clarity</span>
                    <span className="text-zinc-300">{evaluation.clarity}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-400">Completeness</span>
                    <span className="text-zinc-300">{evaluation.completeness}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-400">Developer value</span>
                    <span className="text-zinc-300">{evaluation.developer_value}</span>
                  </div>
                </div>

                {evaluation.feedback && (
                  <p className="mt-3 text-xs text-zinc-400 italic">
                    &ldquo;{evaluation.feedback}&rdquo;
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

