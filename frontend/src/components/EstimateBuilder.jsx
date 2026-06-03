import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

const TIER_META = {
  good:   { label: 'Good',   line: 'Builder Grade',  feel: 'Standard fixtures, clean install' },
  better: { label: 'Better', line: 'DMF / WAC',      feel: 'Architectural recessed, designer decorative' },
  best:   { label: 'Best',   line: 'Ketra',          feel: 'Full-spectrum tunable, magazine-quality light' },
}

function fmtCurrency(n) {
  if (!n && n !== 0) return '—'
  return '$' + Math.round(n).toLocaleString()
}

function TierBar({ pctGood, pctBetter, pctBest, onChange, disabled }) {
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
      {/* Visual bar */}
      <div className="h-2 rounded-full overflow-hidden flex bg-rule/50">
        {pctGood > 0 && <div className="bg-hint/60 transition-all duration-300" style={{ width: `${pctGood}%` }} />}
        {pctBetter > 0 && <div className="bg-gold transition-all duration-300" style={{ width: `${pctBetter}%` }} />}
        {pctBest > 0 && <div className="bg-charcoal transition-all duration-300" style={{ width: `${pctBest}%` }} />}
      </div>

      {/* Three tier cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { key: 'pctGood', value: pctGood, tier: 'good' },
          { key: 'pctBetter', value: pctBetter, tier: 'better' },
          { key: 'pctBest', value: pctBest, tier: 'best' },
        ].map(({ key, value, tier }) => {
          const active = value > 0
          const meta = TIER_META[tier]
          return (
            <div
              key={key}
              className={`rounded border p-4 transition-all duration-200 ${
                active
                  ? tier === 'best' ? 'border-charcoal bg-charcoal/[0.04]'
                  : 'border-gold/60 bg-gold/[0.06]'
                  : 'border-rule bg-white'
              }`}
            >
              <div className="text-[9px] uppercase tracking-[0.22em] text-gold font-medium mb-0.5">
                {meta.label}
              </div>
              <div className="font-serif text-sm text-charcoal mb-1">{meta.line}</div>
              <div className="flex items-baseline gap-1.5 mb-2">
                <input
                  type="number"
                  min={0} max={100}
                  value={value}
                  onChange={e => set(key, e.target.value)}
                  disabled={disabled}
                  className="w-14 text-center font-serif text-xl font-light text-charcoal border-b border-rule bg-transparent focus:border-gold focus:outline-none disabled:opacity-40"
                />
                <span className="text-hint text-sm">%</span>
              </div>
              <div className="text-[11px] text-hint leading-relaxed font-light">{meta.feel}</div>
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

  // Auto-create estimate when sqft is entered (≥500)
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
        pid = r.data.id
        setProjectId(pid)
      }
      const res = await axios.post(`/api/projects/${pid}/estimate`, {
        total_sqft: sqftNum,
        pct_good: pctGood, pct_better: pctBetter, pct_best: pctBest,
        ceiling_height_default: 9,
      })
      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
      setCreated(true)
    } catch (err) {
      if (err.response?.status === 409 && projectId) {
        await recalc(projectId)
        setCreated(true)
      }
    } finally {
      setLoading(false)
    }
  }

  const recalc = async (pid) => {
    pid = pid || projectId
    if (!pid) return
    try {
      const res = await axios.patch(`/api/projects/${pid}/estimate`, {
        total_sqft: sqftNum || undefined,
        pct_good: pctGood, pct_better: pctBetter, pct_best: pctBest,
      })
      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
    } catch (err) { /* silent */ }
  }

  // Recalc on tier changes
  useEffect(() => {
    if (!created) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => recalc(), 400)
    return () => clearTimeout(debounceRef.current)
  }, [pctGood, pctBetter, pctBest])

  const tiersByRoom = {}
  rooms.forEach(r => {
    tiersByRoom[r.assigned_tier] = (tiersByRoom[r.assigned_tier] || 0) + 1
  })

  return (
    <div className="max-w-2xl mx-auto pb-40">

      {/* ── Hero ── */}
      <div className="text-center mb-12 pt-4">
        <div className="text-[10px] uppercase tracking-[0.32em] text-gold font-medium mb-4">
          Livewire Lighting
        </div>
        <h1 className="font-serif text-5xl font-light text-charcoal leading-tight mb-3">
          Lighting Estimate
        </h1>
        <div className="w-10 h-px bg-gold mx-auto mb-4" />
        <p className="text-sm text-hint font-light max-w-md mx-auto leading-relaxed">
          Enter your home's square footage. We'll generate a complete fixture schedule
          with pricing across your selected quality tiers.
        </p>
      </div>

      {/* ── Square Footage Input ── */}
      <div className="bg-white border border-rule rounded-md p-8 mb-4 text-center">
        <label className="text-[9px] uppercase tracking-[0.28em] text-gold font-medium block mb-4">
          Total Square Footage
        </label>
        <input
          type="number"
          min={500}
          step={100}
          value={sqft}
          onChange={e => setSqft(e.target.value)}
          placeholder="2,500"
          className="w-48 text-center font-serif text-5xl font-light text-charcoal border-b-2 border-rule bg-transparent focus:border-gold focus:outline-none placeholder:text-rule transition-colors pb-2"
          autoFocus
        />
        <div className="text-[11px] text-hint mt-3 font-light">
          {sqftNum >= 500
            ? loading
              ? 'Generating room layout...'
              : created
                ? `${rooms.length} rooms generated`
                : 'Press enter or wait — rooms generate automatically'
            : sqftNum > 0
              ? 'Minimum 500 sq ft'
              : 'Total conditioned area of the home'}
        </div>
        {loading && (
          <div className="mt-3 flex justify-center">
            <div className="w-5 h-5 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* ── Tier Allocation (appears after rooms generate) ── */}
      {created && (
        <div className="bg-white border border-rule rounded-md overflow-hidden mb-4 animate-in">
          <div className="px-6 py-4 border-b border-rule/60 flex items-center justify-between">
            <div>
              <div className="text-[9px] uppercase tracking-[0.22em] text-gold font-medium mb-0.5">
                Quality Distribution
              </div>
              <div className="font-serif text-lg text-charcoal font-light">
                Good · Better · Best
              </div>
            </div>
            <div className="text-right">
              <div className="text-[9px] uppercase tracking-[0.22em] text-hint mb-0.5">Rooms</div>
              <div className="flex gap-2">
                {['good', 'better', 'best'].map(t => (
                  <span key={t} className={`text-xs px-1.5 py-0.5 rounded ${
                    t === 'best' ? 'bg-charcoal/10 text-charcoal'
                    : t === 'better' ? 'bg-gold/10 text-gold-dark'
                    : 'bg-hint/10 text-hint'
                  }`}>
                    {tiersByRoom[t] || 0}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="px-6 py-5">
            <TierBar
              pctGood={pctGood} pctBetter={pctBetter} pctBest={pctBest}
              onChange={({ pctGood: g, pctBetter: b, pctBest: be }) => {
                setPctGood(g); setPctBetter(b); setPctBest(be)
              }}
            />
          </div>
        </div>
      )}

      {/* ── Room List (compact, beautiful) ── */}
      {created && rooms.length > 0 && (
        <div className="bg-white border border-rule rounded-md overflow-hidden mb-4">
          <div className="px-6 py-4 border-b border-rule/60">
            <div className="text-[9px] uppercase tracking-[0.22em] text-gold font-medium mb-0.5">
              Room Breakdown
            </div>
            <div className="font-serif text-lg text-charcoal font-light">
              {rooms.length} rooms · {sqftNum.toLocaleString()} sq ft
            </div>
          </div>
          <div className="divide-y divide-rule/40">
            {rooms.map(room => (
              <div key={room.id} className="px-6 py-3 flex items-center justify-between hover:bg-cream/50 transition-colors">
                <div className="flex items-center gap-3">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    room.assigned_tier === 'best' ? 'bg-charcoal'
                    : room.assigned_tier === 'good' ? 'bg-hint/50'
                    : 'bg-gold'
                  }`} />
                  <span className="text-sm text-charcoal">{room.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-hint font-light">{room.sqft ? `${Math.round(room.sqft)} sf` : ''}</span>
                  <span className={`text-[9px] uppercase tracking-[0.16em] font-medium ${
                    room.assigned_tier === 'best' ? 'text-charcoal'
                    : room.assigned_tier === 'good' ? 'text-hint'
                    : 'text-gold'
                  }`}>
                    {room.assigned_tier}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Sticky Footer ── */}
      {created && summary && (
        <div className="fixed bottom-0 left-0 right-0 z-50">
          <div className="max-w-2xl mx-auto">
            <div className="bg-white border-t border-x border-rule rounded-t-lg shadow-[0_-8px_30px_rgba(0,0,0,0.08)] mx-4">
              <div className="flex items-center justify-between px-6 py-4">
                <div>
                  <div className="text-[9px] uppercase tracking-[0.22em] text-hint mb-1">
                    Estimated Investment
                  </div>
                  <div className="font-serif text-3xl font-light text-charcoal leading-none">
                    {fmtCurrency(summary.budget_low)}
                    <span className="text-gold mx-2">—</span>
                    {fmtCurrency(summary.budget_high)}
                  </div>
                  <div className="text-[11px] text-hint mt-1 font-light">
                    {summary.total_fixtures} fixtures · {rooms.length} rooms · excl. tax
                  </div>
                </div>
                <button
                  onClick={() => onComplete(projectId, rooms, summary)}
                  className="px-6 py-3 bg-charcoal text-white text-[10px] uppercase tracking-[0.16em] font-medium rounded-sm hover:bg-charcoal-dark transition-colors"
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
