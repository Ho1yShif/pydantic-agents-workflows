'use client'

import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import QuestionInput from '@/components/QuestionInput'
import ProgressTracker from '@/components/ProgressTracker'
import AnswerDisplay from '@/components/AnswerDisplay'
import MetricsPanel from '@/components/MetricsPanel'
import MetricsSkeleton from '@/components/MetricsSkeleton'
import HistoryPanel from '@/components/HistoryPanel'
import { askQuestion } from '@/lib/api'
import type { AnswerResponse, ProgressUpdate } from '@/types'

export default function Home() {
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<ProgressUpdate[]>([])
  const [answer, setAnswer] = useState<AnswerResponse | null>(null)
  const [streamingAnswer, setStreamingAnswer] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const handleStop = () => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setLoading(false)
    setProgress([])
    setStreamingAnswer('')
    setAnswer(null)
    setError(null)
  }

  const handleAskQuestion = async (question: string) => {
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setProgress([])
    setAnswer(null)
    setStreamingAnswer('')
    setError(null)

    try {
      const result = await askQuestion(
        question,
        (update) => {
          setProgress((prev) => [...prev, update])
        },
        (delta) => {
          setStreamingAnswer((prev) => prev + delta)
        },
        controller.signal
      )

      setAnswer(result)
    } catch (err) {
      if (controller.signal.aborted) {
        return
      }
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleLoadSession = (session: AnswerResponse) => {
    setAnswer(session)
    setProgress([])
    setError(null)
  }

  return (
    <div className="relative z-10 min-h-screen bg-black flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-zinc-800 bg-black/90 backdrop-blur-sm flex-shrink-0">
        <div className="w-full px-4 sm:px-8 lg:px-12 h-24 flex items-end justify-between pb-3">
          <div className="flex flex-col gap-2 items-start">
            <h1 className="title-gradient text-4xl font-bold tracking-tight leading-tight">
              Ask Render Anything
            </h1>
            <p className="text-sm text-zinc-400">
              Observable RAG pipeline • Multi-query retrieval • Claims verification
            </p>
          </div>
          <span className="text-sm text-zinc-400 hidden sm:flex items-center gap-1">
            Powered by{' '}
            <a
              href="https://ai.pydantic.dev/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors duration-200"
            >
              Pydantic AI
            </a>
            {' '}•{' '}Deployed on{' '}
            <a
              href="https://render.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors duration-200"
            >
              Render
            </a>
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-full">
          {/* Left Column - Input & Answer */}
          <div className="lg:col-span-2 space-y-6">
            <QuestionInput onSubmit={handleAskQuestion} loading={loading} onHistoryToggle={() => setHistoryOpen(!historyOpen)} onStop={handleStop} />

            {error && (
              <div className="bg-red-500/10 border border-red-500/50 p-4 transition-colors">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {loading && (
              <ProgressTracker progress={progress} loading={loading} />
            )}

            {loading && streamingAnswer && (
              <div className="bg-black border border-zinc-800 overflow-hidden">
                <div className="border-b border-zinc-800 bg-zinc-900 px-6 py-4">
                  <h2 className="text-xl font-semibold text-white">Answer</h2>
                  <p className="text-sm text-zinc-400 mt-1">Generating...</p>
                </div>
                <div className="px-6 py-6 prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingAnswer}</ReactMarkdown>
                </div>
              </div>
            )}

            {answer && <AnswerDisplay answer={answer} />}
          </div>

          {/* Right Column - Metrics */}
          <div className="lg:col-span-1">
            <div className="lg:sticky lg:top-32">
              {answer ? (
                <MetricsPanel answer={answer} />
              ) : (
                <MetricsSkeleton loading={loading} />
              )}
            </div>
          </div>
        </div>
      </main>

      {/* History Panel */}
      <HistoryPanel
        onLoadSession={handleLoadSession}
        isOpen={historyOpen}
        onToggle={() => setHistoryOpen(!historyOpen)}
      />

      {/* Footer */}
      <footer className="border-t border-zinc-800 bg-black flex-shrink-0">
        <div className="px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between text-sm text-zinc-500">
          <div className="flex items-center gap-6">
            <a
              href="https://ai.pydantic.dev/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors flex items-center gap-1"
            >
              Pydantic AI
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
            <span>•</span>
            <a
              href="https://logfire.pydantic.dev/docs/why/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors flex items-center gap-1"
            >
              Logfire
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
            <span>•</span>
            <a
              href="https://render.com/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors flex items-center gap-1"
            >
              Render Docs
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
            <span>•</span>
            <a
              href="https://github.com/render-examples/logfire-pydantic"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-400 transition-colors flex items-center gap-1"
            >
              GitHub
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
          <span>&copy; Render 2026</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
