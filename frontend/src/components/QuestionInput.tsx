'use client'

import { useState, FormEvent } from 'react'

interface QuestionInputProps {
  onSubmit: (question: string) => void
  loading: boolean
  onHistoryToggle?: () => void
  onStop?: () => void
}

function sanitizeInput(raw: string): string {
  // Strip null bytes and control characters (keep \n \t \r)
  let s = raw.replace(/[\x00\x01-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')
  // Decode HTML entities using native DOM to prevent &lt;script&gt; bypass
  const ta = document.createElement('textarea')
  ta.innerHTML = s
  s = ta.value
  // Strip HTML tags
  s = s.replace(/<[^>]*>/g, '')
  // Strip orphaned angle brackets
  s = s.replace(/[<>]/g, '')
  // Collapse 3+ newlines to 2
  s = s.replace(/\n{3,}/g, '\n\n')
  return s
}

export default function QuestionInput({ onSubmit, loading, onHistoryToggle, onStop }: QuestionInputProps) {
  const [question, setQuestion] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
  }

  const handleAsk = () => {
    if (question.trim() && !loading) {
      onSubmit(question.trim())
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  const exampleQuestions = [
    "How do I deploy an AI agent on Render?",
    "How do I deploy a Node.js app on Render?",
    "What database plans does Render offer?",
    "How does autoscaling work on Render?",
  ]

  return (
    <div className="bg-black border border-zinc-800 p-6">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label htmlFor="question" className="text-sm font-medium text-zinc-300">
              What do you want to know about Render?
            </label>
            {onHistoryToggle && (
              <button
                type="button"
                onClick={onHistoryToggle}
                className="text-sm text-zinc-400 hover:text-purple-400 transition-all duration-200 flex items-center gap-2 px-3 py-1.5 border border-zinc-800 hover:border-purple-800"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                History
              </button>
            )}
          </div>
          <textarea
            id="question"
            rows={4}
            className="w-full px-4 py-3 bg-transparent border border-zinc-700 text-white placeholder-zinc-500 hover:border-zinc-600 resize-none transition-all duration-200 neon-focus"
            placeholder="> How do I deploy an AI agent on Render?"
            value={question}
            onChange={(e) => setQuestion(sanitizeInput(e.target.value))}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <p className="mt-2 text-xs text-zinc-500 flex justify-between">
            <span>{question.length}/500 characters</span>
            <span className="text-zinc-600">Press Enter to submit, Shift+Enter for new line</span>
          </p>
        </div>

        <button
          type="button"
          onClick={loading ? onStop : handleAsk}
          disabled={!loading && !question.trim()}
          className={loading
            ? "w-full px-6 py-3 bg-purple-700 text-white font-medium border border-purple-600 hover:bg-purple-800 hover:border-purple-700 focus:outline-none transition-all duration-200 flex items-center justify-center gap-3"
            : "w-full px-6 py-3 bg-purple-600 text-white font-medium border border-purple-600 hover:bg-purple-700 hover:border-purple-700 hover:shadow-[0_0_15px_#00fff0,0_0_30px_rgba(0,255,240,0.25)] focus:outline-none focus:border-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          }
        >
          {loading ? (
            <>
              <span className="inline-flex items-center justify-center w-5 h-5 bg-white rounded-sm flex-shrink-0" aria-hidden="true" />
              Stop
            </>
          ) : (
            'Ask'
          )}
        </button>
      </form>

      <div className="mt-6 pt-6 border-t border-zinc-800">
        <p className="text-sm text-zinc-400 mb-3">Example questions</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {exampleQuestions.map((exampleQ, idx) => (
            <button
              key={idx}
              onClick={() => { setQuestion(exampleQ); onSubmit(exampleQ) }}
              disabled={loading}
              className="text-left px-3 py-2 text-sm text-zinc-300 bg-transparent hover:bg-zinc-900/40 border border-zinc-700 hover:border-purple-800 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {exampleQ}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

