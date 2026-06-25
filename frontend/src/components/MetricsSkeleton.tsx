'use client'

interface MetricsSkeletonProps {
  loading: boolean
}

export default function MetricsSkeleton({ loading }: MetricsSkeletonProps) {
  return (
    <div className="space-y-6">
      {/* Confidence score Card */}
      <div className="bg-black border border-zinc-800 p-6">
        <h3 className="text-lg font-semibold text-zinc-300 mb-4">Confidence score</h3>
        
        {loading ? (
          // Skeleton loading state
          <>
            <div className="bg-zinc-900/50 border border-zinc-800 p-4 mb-4 animate-pulse">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-3 h-3 rounded-full bg-zinc-800"></div>
                <div className="h-4 w-32 bg-zinc-800 rounded"></div>
              </div>
              <div className="h-10 w-20 bg-zinc-800 rounded mb-2"></div>
              <div className="h-3 w-40 bg-zinc-800 rounded"></div>
            </div>
            <div className="h-4 w-full bg-zinc-900 rounded"></div>
          </>
        ) : (
          // Placeholder state
          <div className="text-center py-8">
            <div className="text-zinc-700 mb-2">
              <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm text-zinc-600">Will appear after analysis</p>
          </div>
        )}
      </div>

      {/* Cost breakdown Card */}
      <div className="bg-black border border-zinc-800 p-6">
        <h3 className="text-lg font-semibold text-zinc-300 mb-4">Cost breakdown</h3>

        {loading ? (
          // Skeleton loading state
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex justify-between items-center py-2 border-b border-zinc-800 last:border-b-0">
                <div className="h-3 w-32 bg-zinc-900 rounded"></div>
                <div className="h-3 w-16 bg-zinc-900 rounded"></div>
              </div>
            ))}
            <div className="mt-4 pt-4 border-t border-zinc-800 flex justify-between">
              <div className="h-4 w-24 bg-zinc-800 rounded"></div>
              <div className="h-4 w-20 bg-zinc-800 rounded"></div>
            </div>
          </div>
        ) : (
          // Placeholder state
          <div className="text-center py-8">
            <div className="text-zinc-700 mb-2">
              <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm text-zinc-600">Per-stage breakdown</p>
          </div>
        )}
      </div>

      {/* Evaluations Card */}
      <div className="bg-black border border-zinc-800 p-6">
        <h3 className="text-lg font-semibold text-zinc-300 mb-4">Evaluations</h3>

        {loading ? (
          // Skeleton loading state
          <div className="space-y-4 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="border-t border-zinc-800 pt-4 first:border-t-0 first:pt-0">
                <div className="flex justify-between items-center mb-3">
                  <div className="h-4 w-20 bg-zinc-800 rounded"></div>
                  <div className="h-4 w-12 bg-zinc-800 rounded"></div>
                </div>
                <div className="space-y-2">
                  {[1, 2, 3, 4].map((j) => (
                    <div key={j} className="flex justify-between">
                      <div className="h-3 w-24 bg-zinc-900 rounded"></div>
                      <div className="h-3 w-8 bg-zinc-900 rounded"></div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          // Placeholder state
          <div className="text-center py-8">
            <div className="text-zinc-700 mb-2">
              <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
            </div>
            <p className="text-sm text-zinc-600">Dual-model scoring</p>
          </div>
        )}
      </div>
    </div>
  )
}

