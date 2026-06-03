import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { TierComparisonCompact, getTierImage } from './TierComparison'

const TIER_META = {
  good:   { label: 'Good',   line: 'Builder Grade',  feel: 'Standard fixtures, clean install' },
  better: { label: 'Better', line: 'DMF / WAC',      feel: 'Architectural recessed, designer decorative' },
  best:   { label: 'Best',   line: 'Ketra',          feel: 'Full-spectrum tunable, magazine-quality light' },
}

const fmt = n => n ? '$' + Math.round(n).toLocaleString() : '—'

function TierBar({ pctGood, pctBetter, pctBest, onChange }) {
  const set = (field, raw) => {
    const v = Math.max(0, Math.min(100, parseInt(raw) || 0))
    const vals = { pctGood, pctBetter, pctBest, [field]: v }
    const others = ['pctGood', 'pctBetter', 'pctBest'].filter(f => f !== field)
    const remain = 100 - v
    const otherSum = others.reduce((s, f) => s + vals[f], 0)
    if (otherSum === 0) { vals[others[0]] = remain; vals[others[1]] = 0 }
    else { const r = remain / otherSum; vals[others[0]] = Math.round(vals[others[0]] * r); vals[others[1]] = 100 - v - vals[others[0]] }
    onChange(vals)
  }

  return (
    <div className="space-y-5">
      <div className="h-2 rounded-full overflow-hidden flex bg-bone-200">
        {pctGood > 0 && <div className="bg-ink-300 transition-all duration-300" style={{ width: `${pctGood}%` }} />}
        {pctBetter > 0 && <div className="bg-copper transition-all duration-300" style={{ width: `${pctBetter}%` }} />}
        {pctBest > 0 && <div className="bg-ink-800 transition-all duration-300" style={{ width: `${pctBest}%` }} />}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[
          { key: 'pctGood', value: pctGood, tier: 'good', border: 'border-ink-200', bg: 'bg-bone-100' },
          { key: 'pctBetter', value: pctBetter, tier: 'better', border: 'border-copper/40', bg: 'bg-copper-50' },
          { key: 'pctBest', value: pctBest, tier: 'best', border: 'border-ink-600', bg: 'bg-ink-800/[0.04]' },
        ].map(({ key, value, tier, border, bg }) => {
          const active = value > 0
          const meta = TIER_META[tier]
          return (
            <div key={key} className={`rounded-md border p-4 transition-all duration-200 ${active ? `${border} ${bg}` : 'border-bone-200 bg-white'}`}>
              <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-0.5">
                {meta.label}
              </div>
              <div className="font-serif text-sm text-ink-700 mb-2 italic">{meta.line}</div>
              <div className="flex items-baseline gap-1.5 mb-2">
                <input
                  type="number" min={0} max={100} value={value}
                  onChange={e => set(key, e.target.value)}
                  className="w-14 text-center font-serif text-xl font-light text-ink-800 border-b border-bone-300 bg-transparent focus:border-copper focus:outline-none"
                />
                <span className="text-ink-400 text-sm">%</span>
              </div>
              <div className="text-[11px] text-ink-400 leading-relaxed">{meta.feel}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function EstimateBuilder({ existingProject, onComplete }) {
  const [sqft, setSqft] = useState('')
  const [pctGood, setPctGood] = useState(20)
  const [pctBetter, setPctBetter] = useState(70)
  const [pctBest, setPctBest] = useState(10)
  const [rooms, setRooms] = useState([])
  const [summary, setSummary] = useState(null)
  const [projectId, setProjectId] = useState(existingProject?.id || null)
  const [loading, setLoading] = useState(false)
  const [created, setCreated] = useState(false)
  const debounceRef = useRef(null)
  const sqftNum = parseInt(sqft) || 0

  useEffect(() => {
    if (sqftNum < 500 || created) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => createEstimate(), 800)
    return () => clearTimeout(debounceRef.current)
  }, [sqftNum])

  const createEstimate = async () => {
    if (sqftNum < 500) return
    setLoading(true)
    try {
      let pid = projectId
      if (!pid) {
        const r = await axios.post('/api/projects', { name: 'New Estimate', tier: 'better' })
        pid = r.data.id; setProjectId(pid)
      }
      const res = await axios.post(`/api/projects/${pid}/estimate`, {
        total_sqft: sqftNum, pct_good: pctGood, pct_better: pctBetter, pct_best: pctBest, ceiling_height_default: 9,
      })
      setRooms(res.data.rooms || []); setSummary(res.data.summary || null); setCreated(true)
    } catch (err) {
      if (err.response?.status === 409 && projectId) { await recalc(projectId); setCreated(true) }
    } finally { setLoading(false) }
  }

  const recalc = async (pid) => {
    pid = pid || projectId; if (!pid) return
    try {
      const res = await axios.patch(`/api/projects/${pid}/estimate`, {
        total_sqft: sqftNum || undefined, pct_good: pctGood, pct_better: pctBetter, pct_best: pctBest,
      })
      setRooms(res.data.rooms || []); setSummary(res.data.summary || null)
    } catch (err) { /* silent */ }
  }

  useEffect(() => {
    if (!created) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => recalc(), 400)
    return () => clearTimeout(debounceRef.current)
  }, [pctGood, pctBetter, pctBest])

  return (
    <div className="max-w-2xl mx-auto pb-40">
      {/* Hero */}
      <div className="text-center mb-12 pt-4">
        <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-4">
          Livewire Lighting
        </div>
        <h1 className="font-serif text-5xl font-light text-ink-800 leading-[0.98] mb-3" style={{ fontVariationSettings: '"opsz" 144, "SOFT" 50' }}>
          Lighting <em className="font-light">Estimate</em>
        </h1>
        <div className="w-10 h-px bg-copper mx-auto mb-4" />
        <p className="text-sm text-ink-400 max-w-md mx-auto leading-relaxed">
          Enter your home's square footage. We'll generate a complete fixture schedule
          with pricing across your selected quality tiers.
        </p>
      </div>

      {/* Square Footage */}
      <div className="bg-white border border-bone-300 rounded-md p-8 mb-4 text-center">
        <label className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold block mb-4">
          Total Square Footage
        </label>
        <input
          type="number" min={500} step={100} value={sqft}
          onChange={e => setSqft(e.target.value)}
          placeholder="2,500"
          className="w-48 text-center font-serif text-5xl font-light text-ink-800 border-b-2 border-bone-200 bg-transparent focus:border-copper focus:outline-none placeholder:text-bone-300 transition-colors pb-2"
          style={{ fontVariationSettings: '"opsz" 144' }}
          autoFocus
        />
        <div className="text-[11px] text-ink-400 mt-3">
          {sqftNum >= 500
            ? loading ? 'Generating room layout...' : created ? `${rooms.length} rooms generated` : 'Rooms generate automatically'
            : sqftNum > 0 ? 'Minimum 500 sq ft' : 'Total conditioned area of the home'}
        </div>
        {loading && (
          <div className="mt-3 flex justify-center">
            <div className="w-5 h-5 border-2 border-copper/30 border-t-copper rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Tier Allocation */}
      {created && (
        <div className="bg-white border border-bone-300 rounded-md overflow-hidden mb-4">
          <div className="px-6 py-4 border-b border-bone-200 flex items-center justify-between">
            <div>
              <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-0.5">Quality Distribution</div>
              <div className="font-serif text-lg text-ink-800 font-light italic">Good · Better · Best</div>
            </div>
          </div>
          <div className="px-6 py-5">
            <TierBar pctGood={pctGood} pctBetter={pctBetter} pctBest={pctBest}
              onChange={({ pctGood: g, pctBetter: b, pctBest: be }) => { setPctGood(g); setPctBetter(b); setPctBest(be) }}
            />
            {/* Tier comparison visual — shows kitchen as the universal example */}
            <div className="mt-5">
              <TierComparisonCompact roomType="kitchen" />
            </div>
          </div>
        </div>
      )}

      {/* Room List */}
      {created && rooms.length > 0 && (
        <div className="bg-white border border-bone-300 rounded-md overflow-hidden mb-4">
          <div className="px-6 py-4 border-b border-bone-200">
            <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-0.5">Room Breakdown</div>
            <div className="font-serif text-lg text-ink-800 font-light italic">
              {rooms.length} rooms · {sqftNum.toLocaleString()} sq ft
            </div>
          </div>
          <div className="divide-y divide-bone-200">
            {rooms.map(room => {
              const hasImage = !!getTierImage(room.room_type)
              return (
                <details key={room.id} className="group">
                  <summary className="px-6 py-3 flex items-center justify-between hover:bg-bone-50 transition-colors cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        room.assigned_tier === 'best' ? 'bg-ink-800' : room.assigned_tier === 'good' ? 'bg-ink-300' : 'bg-copper'
                      }`} />
                      <span className="text-sm text-ink-700">{room.name}</span>
                      {hasImage && (
                        <svg className="w-3 h-3 text-ink-300 group-open:rotate-180 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      )}
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-ink-400">{room.sqft ? `${Math.round(room.sqft)} sf` : ''}</span>
                      <span className={`text-[9px] uppercase tracking-[0.16em] font-semibold ${
                        room.assigned_tier === 'best' ? 'text-ink-700' : room.assigned_tier === 'good' ? 'text-ink-400' : 'text-copper-700'
                      }`}>
                        {room.assigned_tier}
                      </span>
                    </div>
                  </summary>
                  {hasImage && (
                    <div className="px-6 pb-3">
                      <TierComparisonCompact roomType={room.room_type} className="mt-1" />
                    </div>
                  )}
                </details>
              )
            })}
          </div>
        </div>
      )}

      {/* Sticky Footer */}
      {created && summary && (
        <div className="fixed bottom-0 left-0 right-0 z-50">
          <div className="max-w-2xl mx-auto">
            <div className="bg-white border-t border-x border-bone-300 rounded-t-lg shadow-[0_-8px_30px_rgba(0,0,0,0.08)] mx-4">
              <div className="flex items-center justify-between px-6 py-4">
                <div>
                  <div className="text-[10.5px] uppercase tracking-[0.24em] text-ink-400 font-semibold mb-1">Estimated Investment</div>
                  <div className="font-serif text-3xl font-light text-ink-800 leading-none" style={{ fontVariationSettings: '"opsz" 144' }}>
                    {fmt(summary.budget_low)}
                    <span className="text-copper mx-2">—</span>
                    {fmt(summary.budget_high)}
                  </div>
                  <div className="text-[11px] text-ink-400 mt-1">
                    {summary.total_fixtures} fixtures · {rooms.length} rooms · excl. tax
                  </div>
                </div>
                <button
                  onClick={() => onComplete(projectId, rooms, summary)}
                  className="px-6 py-3 bg-copper-500 text-white text-[10.5px] uppercase tracking-[0.16em] font-semibold rounded-full hover:bg-copper-600 transition-colors"
                >
                  View Schedule
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
