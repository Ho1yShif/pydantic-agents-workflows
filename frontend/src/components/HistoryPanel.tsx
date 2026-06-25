'use client'

import { useState, useEffect } from 'react'
import { FaListCheck, FaXmark } from 'react-icons/fa6'
import { getHistory, deleteSession, clearAllHistory, type HistorySession } from '@/lib/api'
import type { AnswerResponse } from '@/types'

interface HistoryPanelProps {
  onLoadSession: (session: AnswerResponse) => void
  isOpen: boolean
  onToggle: () => void
}

export default function HistoryPanel({ onLoadSession, isOpen, onToggle }: HistoryPanelProps) {
  const [sessions, setSessions] = useState<HistorySession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isSelectionMode, setIsSelectionMode] = useState(false)

  useEffect(() => {
    loadHistory()
  }, [])

  const loadHistory = async () => {
    try {
      setLoading(true)
      const history = await getHistory(20)
      setSessions(history)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history')
    } finally {
      setLoading(false)
    }
  }

  const handleSessionClick = (session: HistorySession) => {
    // Convert HistorySession to AnswerResponse format
    const answerResponse: AnswerResponse = {
      question: session.question,
      answer: session.answer,
      sources: session.sources,
      claims: session.claims,
      quality_score: session.quality_score,
      evaluations: session.evaluations,
      iterations: session.iterations,
      total_cost: session.total_cost,
      total_duration_ms: session.total_duration_ms,
      stages: session.stages || [],
      timestamp: session.created_at,
      session_id: session.id
    }
    
    onLoadSession(answerResponse)
    onToggle()
  }

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation() // Prevent triggering the session click
    
    if (!confirm('Delete this question from history?')) {
      return
    }

    try {
      setDeleting(sessionId)
      await deleteSession(sessionId)
      setSessions(sessions.filter(s => s.id !== sessionId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete session')
    } finally {
      setDeleting(null)
    }
  }

  const handleClearAll = async () => {
    if (!confirm(`Delete all ${sessions.length} questions from history? This cannot be undone.`)) {
      setShowClearConfirm(false)
      return
    }

    try {
      setLoading(true)
      await clearAllHistory()
      setSessions([])
      setShowClearConfirm(false)
      setSelectedIds(new Set())
      setIsSelectionMode(false)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear history')
    } finally {
      setLoading(false)
    }
  }

  const toggleSelection = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const newSelected = new Set(selectedIds)
    if (newSelected.has(sessionId)) {
      newSelected.delete(sessionId)
    } else {
      newSelected.add(sessionId)
    }
    setSelectedIds(newSelected)
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === sessions.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(sessions.map(s => s.id)))
    }
  }

  const handleDeleteSelected = async () => {
    const count = selectedIds.size
    if (!confirm(`Delete ${count} selected question${count > 1 ? 's' : ''} from history?`)) {
      return
    }

    try {
      setLoading(true)
      // Delete all selected sessions
      await Promise.all(Array.from(selectedIds).map(id => deleteSession(id)))
      
      // Remove from UI
      setSessions(sessions.filter(s => !selectedIds.has(s.id)))
      setSelectedIds(new Set())
      setIsSelectionMode(false)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete selected sessions')
    } finally {
      setLoading(false)
    }
  }

  const cancelSelection = () => {
    setSelectedIds(new Set())
    setIsSelectionMode(false)
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    if (days < 7) return `${days}d ago`
    return date.toLocaleDateString()
  }

  return (
    <>
      {/* Sliding Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-96 bg-black border-l border-zinc-800 transform transition-transform duration-300 ease-in-out z-40 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-zinc-800">
            {isSelectionMode ? (
              <>
                <div className="flex items-center gap-3">
                  <button
                    onClick={toggleSelectAll}
                    className="flex items-center gap-2 text-sm text-zinc-300 hover:text-white transition-colors"
                  >
                    <div className={`w-5 h-5 border-2 flex items-center justify-center transition-colors ${
                      selectedIds.size === sessions.length && sessions.length > 0
                        ? 'bg-purple-600 border-purple-600'
                        : 'border-zinc-600'
                    }`}>
                      {selectedIds.size === sessions.length && sessions.length > 0 && (
                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span>{selectedIds.size} selected</span>
                  </button>
                  <button
                    onClick={cancelSelection}
                    className="text-sm text-zinc-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-start gap-2">
                <h2 className="text-lg font-semibold text-white">Recent questions</h2>
                {sessions.length > 0 && (
                  <button
                    onClick={() => setIsSelectionMode(true)}
                    className="text-sm text-zinc-400 hover:text-white transition-colors mr-2"
                    title="Select multiple"
                  >
                    <FaListCheck className="w-5 h-5" />
                  </button>
                )}
              </div>
            )}
            <button
              onClick={onToggle}
              className="text-zinc-400 hover:text-white transition-colors"
            >
              <FaXmark className="w-6 h-6" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {loading && (
              <div className="flex items-center justify-center py-8">
                <svg className="animate-spin w-8 h-8 text-purple-600" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/50 text-red-400 text-sm">
                {error}
              </div>
            )}

            {!loading && !error && sessions.length === 0 && (
              <div className="text-center py-8 text-zinc-500">
                <p>No previous questions yet.</p>
                <p className="text-sm mt-2">Ask your first question to get started!</p>
              </div>
            )}

            {!loading && !error && sessions.length > 0 && (
              <div className="space-y-2">
                {sessions.map((session) => {
                  const isSelected = selectedIds.has(session.id)
                  
                  // Calculate confidence score (same as MetricsPanel)
                  const verifiedClaims = session.claims?.filter((c: any) => c.verified).length || 0
                  const totalClaims = session.claims?.length || 0
                  const verificationRate = totalClaims > 0 ? (verifiedClaims / totalClaims) * 100 : 0
                  const confidenceScore = Math.round(
                    (session.quality_score * 0.5) + (verificationRate * 0.5)
                  )
                  
                  return (
                    <div
                      key={session.id}
                      className="group relative"
                    >
                      <button
                        onClick={isSelectionMode ? (e) => toggleSelection(session.id, e) : () => handleSessionClick(session)}
                        disabled={deleting === session.id}
                        className={`w-full text-left p-3 border transition-colors disabled:opacity-50 ${
                          isSelected
                            ? 'bg-purple-900/20 border-purple-600'
                            : 'bg-zinc-900 border-zinc-800 hover:border-purple-600'
                        }`}
                      >
                        {/* Grid: text (top-left), time (top-right), confidence (bottom-left), checkbox (bottom-right) */}
                        <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-2">
                          {/* Top left: Question text */}
                          <p className={`text-sm text-white line-clamp-2 ${!isSelectionMode ? 'pr-8' : ''}`}>
                            {session.question}
                          </p>
                          
                          {/* Top right: Timestamp */}
                          <span className="text-xs text-zinc-500 self-start">
                            {formatDate(session.created_at)}
                          </span>
                          
                          {/* Bottom left: Confidence badge */}
                          <span className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium border w-fit ${
                            confidenceScore >= 85 
                              ? 'bg-green-500/10 border-green-500/50 text-green-400'
                              : confidenceScore >= 70
                              ? 'bg-yellow-500/10 border-yellow-500/50 text-yellow-400'
                              : confidenceScore >= 60
                              ? 'bg-orange-500/10 border-orange-500/50 text-orange-400'
                              : 'bg-red-500/10 border-red-500/50 text-red-400'
                          }`}>
                            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                            {confidenceScore}% confidence
                          </span>
                          
                          {/* Bottom right: Checkbox (only in selection mode) */}
                          {isSelectionMode && (
                            <div className="flex justify-end items-end">
                              <div className={`w-5 h-5 border-2 flex items-center justify-center transition-colors ${
                                isSelected
                                  ? 'bg-purple-600 border-purple-600'
                                  : 'border-zinc-600'
                              }`}>
                                {isSelected && (
                                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                  </svg>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </button>
                      
                      {/* Delete button - appears on hover when not in selection mode */}
                      {!isSelectionMode && (
                        <button
                          onClick={(e) => handleDeleteSession(session.id, e)}
                          disabled={deleting === session.id}
                          className="absolute top-3 right-3 p-1 opacity-0 group-hover:opacity-100 transition-opacity bg-zinc-800 border border-zinc-700 hover:border-red-500 hover:text-red-400 text-zinc-400 disabled:opacity-50"
                          title="Delete"
                        >
                          {deleting === session.id ? (
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                          ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          )}
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-zinc-800 space-y-2">
            {isSelectionMode && selectedIds.size > 0 ? (
              <button
                onClick={handleDeleteSelected}
                disabled={loading}
                className="w-full px-4 py-2 bg-red-600 text-white border border-red-500 hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 font-medium"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete {selectedIds.size} selected
              </button>
            ) : (
              <>
                <button
                  onClick={loadHistory}
                  disabled={loading}
                  className="w-full px-4 py-2 bg-zinc-900 text-zinc-300 border border-zinc-700 hover:border-purple-800 transition-colors disabled:opacity-50"
                >
                  {loading ? 'Refreshing...' : 'Refresh history'}
                </button>
                
                {sessions.length > 0 && !isSelectionMode && (
                  <button
                    onClick={handleClearAll}
                    disabled={loading}
                    className="w-full px-4 py-2 bg-zinc-900 text-red-400 border border-zinc-700 hover:border-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    Clear all history
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30"
          onClick={onToggle}
        />
      )}
    </>
  )
}

