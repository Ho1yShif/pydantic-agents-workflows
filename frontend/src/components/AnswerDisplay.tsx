'use client'

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { AnswerResponse } from '@/types'
import { getSessionLogs, type SessionLogsResponse, type LogfireLog } from '@/lib/api'

interface AnswerDisplayProps {
  answer: AnswerResponse
}

export default function AnswerDisplay({ answer }: AnswerDisplayProps) {
  const [activeTab, setActiveTab] = useState<'answer' | 'claims' | 'sources' | 'pipeline' | 'logs'>('answer')
  const [logs, setLogs] = useState<SessionLogsResponse | null>(null)
  const [logsLoading, setLogsLoading] = useState(false)
  const [logsError, setLogsError] = useState<string | null>(null)
  const [collapsedSpans, setCollapsedSpans] = useState<Set<string>>(new Set())

  const verifiedClaimsCount = answer.claims.filter(c => c.verified).length
  const verificationRate = answer.claims.length > 0
    ? (verifiedClaimsCount / answer.claims.length * 100).toFixed(0)
    : '0'

  // Fetch logs when Logs tab is activated
  useEffect(() => {
    if (activeTab === 'logs' && !logs && !logsLoading && answer.session_id) {
      setLogsLoading(true)
      setLogsError(null)
      
      getSessionLogs(answer.session_id)
        .then(data => {
          setLogs(data)
        })
        .catch(err => {
          setLogsError(err.message || 'Failed to load logs')
        })
        .finally(() => {
          setLogsLoading(false)
        })
    }
  }, [activeTab, logs, logsLoading, answer.session_id])

  return (
    <div className="bg-black border border-zinc-800 overflow-hidden">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900 px-6 py-4">
        <h2 className="text-xl font-semibold text-white">Answer</h2>
        <p className="text-sm text-zinc-400 mt-1">{answer.question}</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-zinc-800">
        <div className="flex gap-1 px-6">
          <button
            onClick={() => setActiveTab('answer')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'answer'
                ? 'border-purple-600 text-purple-600'
                : 'border-transparent text-zinc-400 hover:text-zinc-300'
            }`}
          >
            Answer
          </button>
          <button
            onClick={() => setActiveTab('claims')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'claims'
                ? 'border-purple-600 text-purple-600'
                : 'border-transparent text-zinc-400 hover:text-zinc-300'
            }`}
          >
            Claims ({answer.claims.length})
          </button>
          <button
            onClick={() => setActiveTab('sources')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'sources'
                ? 'border-purple-600 text-purple-600'
                : 'border-transparent text-zinc-400 hover:text-zinc-300'
            }`}
          >
            Sources ({answer.sources.length})
          </button>
          {answer.stages && answer.stages.length > 0 && (
            <button
              onClick={() => setActiveTab('pipeline')}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'pipeline'
                  ? 'border-purple-600 text-purple-600'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              AI pipeline ({answer.stages.length} stages)
            </button>
          )}
          {answer.session_id && (
            <button
              onClick={() => setActiveTab('logs')}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'logs'
                  ? 'border-purple-600 text-purple-600'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              Logs{logs && logs.logs.length > 0 ? ` (${logs.logs.length})` : ''}
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'answer' && (
          <div className="prose prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Table components with dark theme styling
                table: ({node, children, ...props}) => (
                  <div className="overflow-x-auto !my-4">
                    <table className="min-w-full border border-zinc-700 text-sm !m-0" {...props}>
                      {children}
                    </table>
                  </div>
                ),
                thead: ({node, children, ...props}) => (
                  <thead className="bg-zinc-800" {...props}>
                    {children}
                  </thead>
                ),
                tbody: ({node, children, ...props}) => (
                  <tbody className="divide-y divide-zinc-700" {...props}>
                    {children}
                  </tbody>
                ),
                tr: ({node, children, ...props}) => (
                  <tr className="border-b border-zinc-700" {...props}>
                    {children}
                  </tr>
                ),
                th: ({node, children, ...props}) => (
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-300 uppercase tracking-wider border-r border-zinc-700 last:border-r-0" {...props}>
                    {children}
                  </th>
                ),
                td: ({node, children, ...props}) => (
                  <td className="px-4 py-3 text-zinc-200 border-r border-zinc-700 last:border-r-0" {...props}>
                    {children}
                  </td>
                ),
                // Only customize code blocks - let prose handle everything else
                code: ({node, inline, className, children, ...props}: any) => {
                  // Inline code detection: no className (language-*) means inline code
                  const match = /language-(\w+)/.exec(className || '')
                  const isInline = inline || !match
                  
                  if (isInline) {
                    // Inline code like `minInstances` - minimal padding, simple styling
                    return (
                      <code 
                        className="bg-zinc-800/80 px-1.5 py-0.5 rounded text-[0.9em] text-purple-300 font-mono border border-zinc-700/50" 
                        {...props}
                      >
                        {children}
                      </code>
                    )
                  }
                  
                  // Block code from ``` fences - Use SyntaxHighlighter for syntax highlighting
                  const language = match ? match[1] : 'text'
                  
                  return (
                    <SyntaxHighlighter
                      style={vscDarkPlus}
                      language={language}
                      PreTag="div"
                      customStyle={{
                        margin: '1rem 0',
                        padding: '1rem',
                        borderRadius: '0',
                        border: '1px solid rgb(39 39 42)',
                        fontSize: '0.875rem',
                        lineHeight: '1.5',
                        background: 'rgb(24 24 27)',
                      }}
                      codeTagProps={{
                        style: {
                          fontFamily: 'Menlo, Monaco, "Courier New", monospace',
                        }
                      }}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  )
                },
                pre: ({node, children, ...props}) => {
                  // Let the code component handle pre rendering
                  return <>{children}</>
                },
              }}
            >
              {answer.answer}
            </ReactMarkdown>
          </div>
        )}

        {activeTab === 'claims' && (
          <div className="space-y-3">
            <div className="flex items-center gap-4 mb-4 text-sm">
              <span className="text-zinc-400">
                Verification Rate: <span className="text-white font-medium">{verificationRate}%</span>
              </span>
              <span className="text-zinc-400">
                Verified: <span className="text-green-500 font-medium">{verifiedClaimsCount}</span> / <span className="text-zinc-400">{answer.claims.length}</span>
              </span>
            </div>

            {answer.claims.map((claim, idx) => (
              <div
                key={idx}
                className={`p-4 border ${
                  claim.verified
                    ? 'bg-green-500/5 border-green-500/50'
                    : 'bg-yellow-500/5 border-yellow-500/50'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {claim.verified ? (
                      <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-zinc-200">{claim.claim}</p>
                    <p className="text-xs text-zinc-400 mt-1">
                      Confidence: {(claim.verification_score * 100).toFixed(0)}%
                    </p>
                    {claim.supporting_docs.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs text-zinc-500 mb-1">Supporting docs:</p>
                        {claim.supporting_docs.map((doc, docIdx) => (
                          <a
                            key={docIdx}
                            href={doc}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-purple-600 hover:text-purple-500 block truncate"
                          >
                            {doc}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'sources' && (
          <div className="space-y-4">
            {answer.sources.map((source, idx) => (
              <div
                key={idx}
                className="p-4 bg-zinc-900 border border-zinc-700"
              >
                <div className="flex items-start justify-between gap-4 mb-2">
                  <h4 className="text-sm font-medium text-white">
                    {source.metadata.title || 'Document'}
                  </h4>
                  <span className="text-xs text-yellow-500 flex-shrink-0">
                    {(source.similarity_score * 100).toFixed(0)}% match
                  </span>
                </div>
                <p className="text-sm text-zinc-300 mb-3 line-clamp-3">
                  {source.content}
                </p>
                <a
                  href={source.source}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-purple-600 hover:text-purple-500 inline-flex items-center gap-1"
                >
                  View source
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'pipeline' && (
          <div className="space-y-4">
            {/* Overall Summary */}
            <div className="p-4 bg-zinc-900 border border-zinc-800">
              <h3 className="text-sm font-semibold text-white mb-3">Execution summary</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-zinc-400">Iterations:</span>
                  <span className="ml-2 text-white font-medium">{answer.iterations}</span>
                </div>
                <div>
                  <span className="text-zinc-400">Total Duration:</span>
                  <span className="ml-2 text-white font-medium">
                    {answer.total_duration_ms < 1000
                      ? `${answer.total_duration_ms.toFixed(0)}ms`
                      : `${(answer.total_duration_ms / 1000).toFixed(2)}s`}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-400">Total Cost:</span>
                  <span className="ml-2 text-white font-medium">${answer.total_cost.toFixed(4)}</span>
                </div>
                <div>
                  <span className="text-zinc-400">Quality Score:</span>
                  <span className="ml-2 text-white font-medium">{answer.quality_score.toFixed(1)}/100</span>
                </div>
              </div>
            </div>

            {/* Pipeline Stages - Compact Format */}
            <div className="space-y-2">
              {answer.stages.map((stage, index) => {
                // Format stage name - remove iteration suffix
                const stageName = stage.stage
                  .split('_')
                  .filter(word => word !== 'iter' && !/^\d+$/.test(word))
                  .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                  .join(' ')
                
                // Build compact metadata string
                const metadataStrings = []
                if (stage.metadata) {
                  const m = stage.metadata
                  if (m.documents_retrieved) metadataStrings.push(`${m.documents_retrieved} docs`)
                  if (m.claims_extracted) metadataStrings.push(`${m.claims_extracted} claims`)
                  if (m.claims_verified !== undefined && m.total_claims !== undefined) {
                    metadataStrings.push(`${m.claims_verified}/${m.total_claims} verified`)
                  }
                  if (m.verification_rate) metadataStrings.push(m.verification_rate)
                  if (m.accuracy_score !== undefined) metadataStrings.push(`Accuracy: ${m.accuracy_score}`)
                  if (m.quality_score) metadataStrings.push(`Quality: ${m.quality_score}`)
                  if (m.answer_length) metadataStrings.push(`${m.answer_length} chars`)
                  if (m.embedding_dimensions) metadataStrings.push(`${m.embedding_dimensions}D`)
                }
                
                // Add duration and cost
                const duration = stage.duration_ms < 1000 
                  ? `${stage.duration_ms.toFixed(0)}ms` 
                  : `${(stage.duration_ms / 1000).toFixed(2)}s`
                const cost = `$${stage.cost_usd.toFixed(4)}`
                
                return (
                  <div
                    key={`${stage.stage}-${index}`}
                    className={`flex items-start gap-3 px-4 py-3 border-l-2 ${
                      stage.success
                        ? 'border-green-500/50 bg-zinc-900/50'
                        : 'border-red-500/50 bg-red-500/5'
                    }`}
                  >
                    <div className={`mt-0.5`}>
                      {stage.success ? (
                        <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <div className="flex-1 min-w-0 flex items-baseline justify-between gap-3">
                      <div className="text-sm text-white flex-1">
                        <span className="font-medium">{stageName}</span>
                        {metadataStrings.length > 0 && (
                          <span className="text-zinc-400"> — {metadataStrings.join(' • ')}</span>
                        )}
                        {stage.error && (
                          <span className="text-red-400"> — {stage.error}</span>
                        )}
                      </div>
                      <span className="text-xs text-zinc-500 whitespace-nowrap">{duration} • {cost}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-4">
            {/* Logfire Header */}
            <div className="flex items-center gap-3 pb-2 border-b border-zinc-800">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 139 120" className="h-8 w-auto">
                <path fill="#fff" d="M137.542 90.563 73.808 2.241c-2.006-2.757-6.632-2.757-8.617 0L1.456 90.563a5.318 5.318 0 0 0-.998 3.101 5.331 5.331 0 0 0 3.642 5.05l63.735 20.851h.01a5.31 5.31 0 0 0 3.293 0h.01l63.735-20.85a5.265 5.265 0 0 0 3.393-3.406 5.244 5.244 0 0 0-.749-4.746h.015Zm-68.04-76.151 25.545 35.403-23.889-7.813c-.184-.06-.38-.05-.564-.094a3.488 3.488 0 0 0-.549-.09c-.184-.025-.359-.095-.543-.095-.185 0-.355.07-.54.095-.184.02-.368.05-.548.09-.19.035-.384.035-.554.094L44.115 49.77l-.15.05L69.513 14.41h-.01ZM33.408 64.438l27.811-9.104 2.969-.967v52.838L14.324 90.887l19.084-26.449Zm41.412 42.757V54.367l30.78 10.071 19.085 26.434-49.87 16.323h.005Z"/>
              </svg>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-white">Logfire</h3>
                <p className="text-xs text-zinc-400">Complete execution trace with timing and metadata</p>
              </div>
            </div>
            
            {logsLoading && (
              <div className="flex items-center justify-center py-8">
                <div className="text-zinc-400">Loading logs...</div>
              </div>
            )}
            
            {logsError && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400">
                <strong>Error:</strong> {logsError}
              </div>
            )}
            
            {logs && !logsLoading && !logsError && (
              <div className="space-y-4">
                {/* Trace ID Header */}
                <div className="p-4 bg-zinc-900 border border-zinc-800">
                  <div className="text-xs text-zinc-500 mb-1">Trace ID</div>
                  <div className="text-sm text-white font-mono">{logs.trace_id}</div>
                </div>

                {/* Logs List */}
                {logs.logs.length === 0 ? (
                  <div className="text-center py-8 text-zinc-400">
                    No logs available for this session
                  </div>
                ) : (
                  <div className="space-y-1">
                    {(() => {
                      // Build parent-child map
                      const spanMap = new Map<string, any>()
                      const rootSpans: any[] = []
                      const childrenMap = new Map<string, any[]>()
                      
                      logs.logs.forEach((log: any) => {
                        const spanId = log.span_id
                        const parentSpanId = log.parent_span_id
                        
                        spanMap.set(spanId, log)
                        
                        if (!parentSpanId) {
                          rootSpans.push(log)
                        } else {
                          if (!childrenMap.has(parentSpanId)) {
                            childrenMap.set(parentSpanId, [])
                          }
                          childrenMap.get(parentSpanId)!.push(log)
                        }
                      })
                      
                      // Recursive render function
                      const renderLog = (log: any, depth: number = 0): React.ReactElement[] => {
                        const spanId = log.span_id
                        const children = childrenMap.get(spanId) || []
                        const isCollapsed = collapsedSpans.has(spanId)
                        const hasChildren = children.length > 0
                        
                        const elements: React.ReactElement[] = []
                        
                        elements.push(
                          <div key={spanId} className="space-y-1">
                            <div className={`p-3 bg-zinc-900/50 border border-zinc-800 hover:border-zinc-700 transition-colors ${depth > 0 ? 'ml-' + (depth * 6) : ''}`}
                                 style={{ marginLeft: depth > 0 ? `${depth * 1.5}rem` : '0' }}>
                              <div className="flex items-start gap-3">
                                {/* Collapse/Expand button */}
                                {hasChildren && (
                                  <button
                                    onClick={() => {
                                      const newCollapsed = new Set(collapsedSpans)
                                      if (isCollapsed) {
                                        newCollapsed.delete(spanId)
                                      } else {
                                        newCollapsed.add(spanId)
                                      }
                                      setCollapsedSpans(newCollapsed)
                                    }}
                                    className="text-zinc-500 hover:text-zinc-300 transition-colors mt-0.5"
                                  >
                                    {isCollapsed ? (
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                      </svg>
                                    ) : (
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                      </svg>
                                    )}
                                  </button>
                                )}
                                {!hasChildren && <div className="w-4" />}
                                
                                {(() => {
                                  const timestamp = new Date(log.start_timestamp).toLocaleTimeString('en-US', {
                                    hour12: false,
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    second: '2-digit',
                                    fractionalSecondDigits: 3
                                  })
                                  const message = log.message
                                  const levelNum = log.level
                                  const spanName = log.span_name
                                  
                                  let level = 'info'
                                  let levelColor = 'text-blue-400'
                                  let levelBg = 'bg-blue-500/20'
                                  
                                  if (levelNum >= 17) {
                                    level = 'error'
                                    levelColor = 'text-red-400'
                                    levelBg = 'bg-red-500/20'
                                  } else if (levelNum >= 13) {
                                    level = 'warn'
                                    levelColor = 'text-yellow-400'
                                    levelBg = 'bg-yellow-500/20'
                                  } else if (levelNum >= 9) {
                                    level = 'info'
                                    levelColor = 'text-blue-400'
                                    levelBg = 'bg-blue-500/20'
                                  } else if (levelNum >= 5) {
                                    level = 'debug'
                                    levelColor = 'text-zinc-400'
                                    levelBg = 'bg-zinc-800'
                                  } else {
                                    level = 'trace'
                                    levelColor = 'text-zinc-500'
                                    levelBg = 'bg-zinc-900'
                                  }

                                  const attrs = typeof log.attributes === 'string' 
                                    ? JSON.parse(log.attributes) 
                                    : (log.attributes || {})
                                  
                                  // Try multiple possible attribute names for model
                                  const model = attrs['gen_ai.request.model'] 
                                    || attrs['gen_ai.response.model']
                                    || attrs['llm.request.model']
                                    || attrs['model']
                                    || attrs['request_data.model']
                                  
                                  const inputTokens = attrs['gen_ai.usage.input_tokens'] 
                                    || attrs['input_tokens']
                                  const outputTokens = attrs['gen_ai.usage.output_tokens']
                                    || attrs['output_tokens']
                                  const cost = attrs['cost_usd']
                                  const duration = attrs['duration_ms']
                                  
                                  return (
                                    <>
                                      <div className="text-xs text-zinc-500 font-mono whitespace-nowrap">
                                        {timestamp}
                                      </div>
                                      <div className={`text-xs font-medium px-2 py-0.5 rounded ${levelBg} ${levelColor} uppercase whitespace-nowrap`}>
                                        {level}
                                      </div>
                                      <div className="flex-1 min-w-0">
                                        {spanName && spanName !== message && (
                                          <div className="text-xs text-zinc-500 mb-1">{spanName}</div>
                                        )}
                                        <div className="text-sm text-white break-words">
                                          {message}
                                          {hasChildren && (
                                            <span className="ml-2 text-xs text-zinc-500">
                                              ({children.length} {children.length === 1 ? 'child' : 'children'})
                                            </span>
                                          )}
                                        </div>
                                        
                                        {(model || inputTokens || cost || duration) && (
                                          <div className="mt-2 pt-2 border-t border-zinc-700 flex flex-wrap gap-3 text-xs">
                                            {model && (
                                              <span className="text-zinc-400">
                                                <span className="text-zinc-500">Model:</span> <span className="text-purple-400 font-medium">{model}</span>
                                              </span>
                                            )}
                                            {inputTokens && (
                                              <span className="text-zinc-400">
                                                <span className="text-zinc-500">In:</span> <span className="text-blue-400 font-mono">{inputTokens.toLocaleString()}</span>
                                              </span>
                                            )}
                                            {outputTokens && (
                                              <span className="text-zinc-400">
                                                <span className="text-zinc-500">Out:</span> <span className="text-green-400 font-mono">{outputTokens.toLocaleString()}</span>
                                              </span>
                                            )}
                                            {cost && (
                                              <span className="text-zinc-400">
                                                <span className="text-zinc-500">Cost:</span> <span className="text-yellow-400 font-mono">${cost.toFixed(4)}</span>
                                              </span>
                                            )}
                                            {duration && (
                                              <span className="text-zinc-400">
                                                <span className="text-zinc-500">Duration:</span> <span className="text-cyan-400 font-mono">
                                                  {duration < 1000 ? `${duration.toFixed(0)}ms` : `${(duration / 1000).toFixed(2)}s`}
                                                </span>
                                              </span>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </>
                                  )
                                })()}
                              </div>
                            </div>
                            
                            {/* Render children if not collapsed */}
                            {!isCollapsed && children.map((child: any) => 
                              renderLog(child, depth + 1)
                            )}
                          </div>
                        )
                        
                        return elements
                      }
                      
                      // Render all root spans and their children
                      return rootSpans.map(log => renderLog(log, 0))
                    })()}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

