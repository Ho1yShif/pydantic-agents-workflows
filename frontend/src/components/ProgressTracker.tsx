'use client'

import { ProgressUpdate } from '@/types'

interface ProgressTrackerProps {
  progress: ProgressUpdate[]
  loading: boolean
}

export default function ProgressTracker({ progress, loading }: ProgressTrackerProps) {
  const currentProgress = progress.length > 0 ? progress[progress.length - 1].progress : 0
  const latestUpdate = progress.length > 0 ? progress[progress.length - 1] : null

  const formatStageName = (stage: string) => {
    // Remove "iter_X" or "Iter X" from stage names
    let name = stage.replace(/[_\s]iter[_\s]\d+/gi, '')
    
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  return (
    <div className="bg-black border border-zinc-800 p-4 space-y-3">
      {/* Current Status Bar */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {latestUpdate && (
            <>
              <span className="relative flex-shrink-0 w-4 h-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00fff0] opacity-30"></span>
                <svg className="animate-spin relative w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </span>
              <span className="text-sm text-zinc-300 truncate">
                {formatStageName(latestUpdate.stage)}
              </span>
              <span className="text-xs text-zinc-500 hidden sm:block truncate">
                {latestUpdate.message}
              </span>
            </>
          )}
          {!latestUpdate && loading && (
            <>
              <span className="relative flex-shrink-0 w-4 h-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00fff0] opacity-30"></span>
                <svg className="animate-spin relative w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </span>
              <span className="text-sm text-zinc-300">Initializing...</span>
            </>
          )}
        </div>
        
        <div className="flex items-center gap-3 text-xs flex-shrink-0">
          <span className="text-zinc-400">{currentProgress.toFixed(0)}%</span>
          {latestUpdate && (
            <span className="text-yellow-500">${latestUpdate.cost_so_far.toFixed(4)}</span>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-zinc-900 h-1.5">
        <div
          className="h-full transition-all duration-300 ease-out"
          style={{ width: `${currentProgress}%`, background: 'linear-gradient(90deg, #8b5cf6, #00fff0)' }}
        />
      </div>

      {/* Stage History */}
      {progress.length > 0 && (
        <div className="space-y-1 text-xs">
          {progress.filter(p => p.status === 'completed').slice(-6).map((update, idx) => (
            <div key={idx} className="flex items-center gap-2 text-zinc-500">
              <span className="text-green-500">✓</span>
              <span>{formatStageName(update.stage)}</span>
              <span className="text-zinc-600">—</span>
              <span className="flex-1 truncate">{update.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

