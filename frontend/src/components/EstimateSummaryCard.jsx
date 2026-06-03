const TIER_META = {
  good: { label: 'Good', line: 'Builder Grade', dot: 'bg-ink-300' },
  better: { label: 'Better', line: 'DMF / WAC', dot: 'bg-copper' },
  best: { label: 'Best', line: 'Ketra', dot: 'bg-ink-800' },
}

const fmt = n => n ? '$' + Math.round(n).toLocaleString() : '—'

export default function EstimateSummaryCard({ summary, rooms, pctGood, pctBetter, pctBest }) {
  if (!summary) return null
  const tierCounts = summary.rooms_by_tier || {}

  return (
    <div className="bg-white border border-bone-300 rounded-md overflow-hidden">
      <div className="px-6 py-4 border-b border-bone-200">
        <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-0.5">Estimate Summary</div>
        <div className="font-serif text-lg text-ink-800 font-light italic">Investment Overview</div>
      </div>

      <div className="p-6 space-y-6">
        {/* Budget hero */}
        <div className="text-center py-5">
          <div className="text-[10.5px] uppercase tracking-[0.24em] text-ink-400 font-semibold mb-3">Estimated Investment</div>
          <div className="font-serif text-4xl font-light text-ink-800 leading-none" style={{ fontVariationSettings: '"opsz" 144' }}>
            {fmt(summary.budget_low)}
            <span className="text-copper mx-2 text-2xl">—</span>
            {fmt(summary.budget_high)}
          </div>
          <div className="text-[11px] text-ink-400 mt-2">Excluding applicable tax</div>
        </div>

        <div className="h-px bg-bone-200" />

        {/* Tier bar */}
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-3">Tier Allocation</div>
          <div className="h-2 rounded-full overflow-hidden flex bg-bone-200 mb-4">
            {pctGood > 0 && <div className="bg-ink-300 transition-all duration-300" style={{ width: `${pctGood}%` }} />}
            {pctBetter > 0 && <div className="bg-copper transition-all duration-300" style={{ width: `${pctBetter}%` }} />}
            {pctBest > 0 && <div className="bg-ink-800 transition-all duration-300" style={{ width: `${pctBest}%` }} />}
          </div>
          <div className="grid grid-cols-3 gap-3">
            {['good', 'better', 'best'].map(tier => {
              const pct = tier === 'good' ? pctGood : tier === 'better' ? pctBetter : pctBest
              const count = tierCounts[tier] || 0
              return (
                <div key={tier} className="text-center">
                  <div className="flex items-center justify-center gap-1.5 mb-0.5">
                    <span className={`w-2 h-2 rounded-full ${TIER_META[tier].dot}`} />
                    <span className="font-serif text-base text-ink-800">{pct}%</span>
                  </div>
                  <div className="text-[9px] uppercase tracking-[0.16em] text-ink-400 font-semibold">{TIER_META[tier].label}</div>
                  <div className="text-[11px] text-ink-400">{count} room{count !== 1 ? 's' : ''}</div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="h-px bg-bone-200" />

        {/* Metrics */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-bone-50 rounded-md p-4 text-center">
            <div className="font-serif text-3xl font-light text-ink-800 leading-none mb-1">{summary.total_fixtures}</div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-ink-400 font-semibold">Fixtures</div>
          </div>
          <div className="bg-bone-50 rounded-md p-4 text-center">
            <div className="font-serif text-3xl font-light text-ink-800 leading-none mb-1">{summary.total_prewires}</div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-ink-400 font-semibold">Pre-wires</div>
          </div>
        </div>

        {/* By type */}
        {summary.fixtures_by_type && Object.keys(summary.fixtures_by_type).length > 0 && (
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-3">By Type</div>
            <div className="space-y-2">
              {Object.entries(summary.fixtures_by_type).sort(([, a], [, b]) => b - a).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm text-ink-500 capitalize">{type.replace(/_/g, ' ')}</span>
                  <span className="font-serif text-base text-ink-800">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Room details */}
        {rooms && rooms.length > 0 && (
          <details className="group">
            <summary className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 cursor-pointer hover:text-copper-600 transition-colors font-semibold select-none">
              Room Details · {rooms.length} rooms
            </summary>
            <div className="mt-3 divide-y divide-bone-100">
              {rooms.map(room => (
                <div key={room.id} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      room.assigned_tier === 'best' ? 'bg-ink-800' : room.assigned_tier === 'good' ? 'bg-ink-300' : 'bg-copper'
                    }`} />
                    <span className="text-sm text-ink-700">{room.name}</span>
                  </div>
                  <span className="text-xs text-ink-400">{room.fixtures?.length || 0}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}
