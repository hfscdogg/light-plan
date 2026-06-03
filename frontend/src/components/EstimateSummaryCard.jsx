const TIER_LABELS = {
  good: { label: 'Good', line: 'Builder Grade', color: 'bg-gray-400' },
  better: { label: 'Better', line: 'DMF / WAC', color: 'bg-gold' },
  best: { label: 'Best', line: 'Ketra', color: 'bg-gold-dark' },
}

const FIXTURE_ICONS = {
  recessed: '⊕',
  pendant: '◉',
  sconce: 'D',
  ceiling_fan: '⊗',
  coach_light: '◇',
  exhaust_fan: '⊞',
  under_cabinet: '━',
  landscape: '☘',
  switched_outlet: '⏻',
}

function fmtCurrency(n) {
  if (!n) return '$0'
  return '$' + Math.round(n).toLocaleString()
}

export default function EstimateSummaryCard({ summary, rooms, pctGood, pctBetter, pctBest }) {
  if (!summary) return null

  const tierCounts = summary.rooms_by_tier || {}

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
      <div className="bg-charcoal-light px-5 py-3">
        <h3 className="text-white text-sm font-medium tracking-wide">Estimate Summary</h3>
      </div>

      <div className="p-5 space-y-5">
        {/* Budget range — hero number */}
        <div className="text-center py-4 border-b border-gray-100">
          <div className="text-[9px] uppercase tracking-[0.22em] text-gray-400 mb-2">Estimated Investment</div>
          <div className="text-3xl font-light text-charcoal">
            {fmtCurrency(summary.budget_low)} – {fmtCurrency(summary.budget_high)}
          </div>
          <div className="text-xs text-gray-400 mt-1">Excluding applicable tax</div>
        </div>

        {/* Tier allocation bar */}
        <div>
          <div className="text-[9px] uppercase tracking-[0.22em] text-gray-400 mb-2">Tier Allocation</div>
          <div className="h-2.5 rounded-full overflow-hidden flex bg-gray-100 mb-3">
            {pctGood > 0 && <div className="bg-gray-400 transition-all" style={{ width: `${pctGood}%` }} />}
            {pctBetter > 0 && <div className="bg-gold transition-all" style={{ width: `${pctBetter}%` }} />}
            {pctBest > 0 && <div className="bg-gold-dark transition-all" style={{ width: `${pctBest}%` }} />}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {['good', 'better', 'best'].map(tier => {
              const pct = tier === 'good' ? pctGood : tier === 'better' ? pctBetter : pctBest
              const count = tierCounts[tier] || 0
              return (
                <div key={tier} className="text-xs">
                  <div className="font-medium text-charcoal">{pct}% {TIER_LABELS[tier].label}</div>
                  <div className="text-gray-400">{count} room{count !== 1 ? 's' : ''}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Key metrics */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 rounded p-3">
            <div className="text-2xl font-light text-charcoal">{summary.total_fixtures}</div>
            <div className="text-[10px] uppercase tracking-wider text-gray-400">Total Fixtures</div>
          </div>
          <div className="bg-gray-50 rounded p-3">
            <div className="text-2xl font-light text-charcoal">{summary.total_prewires}</div>
            <div className="text-[10px] uppercase tracking-wider text-gray-400">Pre-wires</div>
          </div>
        </div>

        {/* Fixtures by type */}
        <div>
          <div className="text-[9px] uppercase tracking-[0.22em] text-gray-400 mb-2">Fixture Breakdown</div>
          <div className="space-y-1.5">
            {Object.entries(summary.fixtures_by_type || {})
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gold w-4 text-center">{FIXTURE_ICONS[type] || '•'}</span>
                    <span className="text-gray-600 capitalize">{type.replace(/_/g, ' ')}</span>
                  </div>
                  <span className="text-charcoal font-medium">{count}</span>
                </div>
              ))}
          </div>
        </div>

        {/* Room list (collapsible) */}
        {rooms && rooms.length > 0 && (
          <details className="group">
            <summary className="text-[9px] uppercase tracking-[0.22em] text-gold cursor-pointer hover:text-gold-dark transition-colors font-medium">
              Room Details ({rooms.length} rooms)
            </summary>
            <div className="mt-2 space-y-1">
              {rooms.map(room => (
                <div key={room.id} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-b-0 text-xs">
                  <div>
                    <span className="text-charcoal">{room.name}</span>
                    <span className={`ml-2 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
                      room.assigned_tier === 'best' ? 'bg-gold-dark/10 text-gold-dark' :
                      room.assigned_tier === 'good' ? 'bg-gray-100 text-gray-500' :
                      'bg-gold/10 text-gold'
                    }`}>
                      {room.assigned_tier}
                    </span>
                  </div>
                  <span className="text-gray-400">{room.fixtures?.length || 0} fixtures</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}
