import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

const ROOM_TYPES = [
  'kitchen', 'dining', 'living', 'family', 'great_room',
  'master_bedroom', 'bedroom', 'master_bathroom', 'bathroom', 'half_bath',
  'hallway', 'entry', 'foyer', 'laundry', 'mudroom', 'pantry',
  'office', 'den', 'bonus_room', 'closet', 'walk_in_closet',
  'garage', 'porch', 'patio',
]

const TIER_INFO = {
  good: { label: 'Good', line: 'Builder Grade', color: 'bg-gray-400', desc: 'Halo, Commercial Electric — standard recessed, basic sconces' },
  better: { label: 'Better', line: 'DMF / WAC', color: 'bg-gold', desc: 'DMF DID Series 2" architectural recessed, WAC decorative' },
  best: { label: 'Best', line: 'Ketra', color: 'bg-gold-dark', desc: 'Ketra S38 full-spectrum tunable, premium linear accent' },
}

const CEILING_HEIGHTS = [8, 9, 10, 12]

function Section({ num, title, subtitle, defaultOpen = true, children, complete }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="bg-white border border-gray-200 rounded-md mb-3 overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-3">
          <div className={`w-6 h-6 rounded-full text-xs font-medium flex items-center justify-center flex-shrink-0 ${
            complete ? 'bg-charcoal text-white' : 'bg-gray-100 text-gray-500'
          }`}>
            {complete ? '✓' : num}
          </div>
          <div className="text-left">
            <div className="text-sm font-medium text-charcoal">{title}</div>
            {subtitle && <div className="text-xs text-gray-500 mt-0.5">{subtitle}</div>}
          </div>
        </div>
        <svg className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100">
          {children}
        </div>
      )}
    </div>
  )
}

function TierBar({ pctGood, pctBetter, pctBest, onChange }) {
  const handleChange = (field, value) => {
    const v = Math.max(0, Math.min(100, parseInt(value) || 0))
    const others = { pctGood, pctBetter, pctBest, [field]: v }

    // Auto-balance: adjust the other two proportionally
    const remaining = 100 - v
    const otherFields = ['pctGood', 'pctBetter', 'pctBest'].filter(f => f !== field)
    const otherSum = otherFields.reduce((s, f) => s + others[f], 0)

    if (otherSum === 0) {
      others[otherFields[0]] = remaining
      others[otherFields[1]] = 0
    } else {
      const ratio = remaining / otherSum
      others[otherFields[0]] = Math.round(others[otherFields[0]] * ratio)
      others[otherFields[1]] = 100 - v - others[otherFields[0]]
    }

    onChange(others)
  }

  return (
    <div className="mt-4 space-y-4">
      {/* Visual bar */}
      <div className="h-3 rounded-full overflow-hidden flex bg-gray-100">
        {pctGood > 0 && (
          <div className="bg-gray-400 transition-all" style={{ width: `${pctGood}%` }} />
        )}
        {pctBetter > 0 && (
          <div className="bg-gold transition-all" style={{ width: `${pctBetter}%` }} />
        )}
        {pctBest > 0 && (
          <div className="bg-gold-dark transition-all" style={{ width: `${pctBest}%` }} />
        )}
      </div>

      {/* Three columns */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { key: 'pctGood', value: pctGood, tier: 'good' },
          { key: 'pctBetter', value: pctBetter, tier: 'better' },
          { key: 'pctBest', value: pctBest, tier: 'best' },
        ].map(({ key, value, tier }) => (
          <div key={key} className={`p-4 rounded border ${value > 0 ? 'border-gold bg-gold/5' : 'border-gray-200 bg-white'}`}>
            <div className="text-[10px] uppercase tracking-widest text-gold font-medium mb-1">
              {TIER_INFO[tier].label}
            </div>
            <div className="text-xs text-gray-500 mb-2">{TIER_INFO[tier].line}</div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                max={100}
                value={value}
                onChange={e => handleChange(key, e.target.value)}
                className="w-16 px-2 py-1.5 text-sm border border-gray-300 rounded text-center focus:border-gold focus:outline-none"
              />
              <span className="text-sm text-gray-400">%</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-2 leading-relaxed">{TIER_INFO[tier].desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RoomRow({ room, onUpdate, onDelete }) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-100 last:border-b-0 group">
      <div className="flex-1 min-w-0">
        <input
          type="text"
          value={room.name}
          onChange={e => onUpdate({ ...room, name: e.target.value })}
          className="text-sm text-charcoal bg-transparent border-b border-transparent hover:border-gray-300 focus:border-gold focus:outline-none w-full py-0.5"
        />
      </div>
      <select
        value={room.room_type}
        onChange={e => onUpdate({ ...room, room_type: e.target.value })}
        className="text-xs text-gray-500 bg-transparent border border-gray-200 rounded px-2 py-1 focus:border-gold focus:outline-none"
      >
        {ROOM_TYPES.map(t => (
          <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
        ))}
      </select>
      <input
        type="number"
        value={room.sqft || ''}
        onChange={e => onUpdate({ ...room, sqft: parseInt(e.target.value) || 0 })}
        placeholder="sqft"
        className="w-20 text-sm text-right border border-gray-200 rounded px-2 py-1 focus:border-gold focus:outline-none"
      />
      <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded font-medium ${
        room.assigned_tier === 'best' ? 'bg-gold-dark/10 text-gold-dark' :
        room.assigned_tier === 'good' ? 'bg-gray-100 text-gray-500' :
        'bg-gold/10 text-gold'
      }`}>
        {room.assigned_tier || 'better'}
      </span>
      <button
        onClick={onDelete}
        className="text-gray-300 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

export default function EstimateBuilder({ existingProject, onComplete }) {
  const [name, setName] = useState(existingProject?.name || '')
  const [address, setAddress] = useState(existingProject?.address || '')
  const [sqft, setSqft] = useState(2500)
  const [stories, setStories] = useState(1)
  const [ceilingHeight, setCeilingHeight] = useState(9)
  const [pctGood, setPctGood] = useState(20)
  const [pctBetter, setPctBetter] = useState(70)
  const [pctBest, setPctBest] = useState(10)
  const [rooms, setRooms] = useState([])
  const [summary, setSummary] = useState(null)
  const [projectId, setProjectId] = useState(existingProject?.id || null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [estimateCreated, setEstimateCreated] = useState(false)
  const debounceRef = useRef(null)

  // Create project + estimate on first sqft entry
  const createEstimate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let pid = projectId
      if (!pid) {
        const projRes = await axios.post('/api/projects', {
          name: name || 'New Estimate',
          address: address || null,
          tier: 'better',
        })
        pid = projRes.data.id
        setProjectId(pid)
      }

      const res = await axios.post(`/api/projects/${pid}/estimate`, {
        total_sqft: sqft,
        num_stories: stories,
        pct_good: pctGood,
        pct_better: pctBetter,
        pct_best: pctBest,
        ceiling_height_default: ceilingHeight,
      })

      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
      setEstimateCreated(true)
    } catch (err) {
      if (err.response?.status === 409 && pid) {
        await updateEstimate(pid)
        setEstimateCreated(true)
      } else {
        setError(err.response?.data?.detail || 'Failed to create estimate')
      }
    } finally {
      setLoading(false)
    }
  }, [projectId, name, address, sqft, stories, pctGood, pctBetter, pctBest, ceilingHeight])

  const updateEstimate = useCallback(async (pid) => {
    pid = pid || projectId
    if (!pid) return

    try {
      const res = await axios.patch(`/api/projects/${pid}/estimate`, {
        total_sqft: sqft,
        pct_good: pctGood,
        pct_better: pctBetter,
        pct_best: pctBest,
        ceiling_height_default: ceilingHeight,
      })
      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
    } catch (err) {
      console.error('Failed to update estimate:', err)
    }
  }, [projectId, sqft, pctGood, pctBetter, pctBest, ceilingHeight])

  // Debounced update when tier percentages change
  useEffect(() => {
    if (!estimateCreated) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => updateEstimate(), 400)
    return () => clearTimeout(debounceRef.current)
  }, [pctGood, pctBetter, pctBest, ceilingHeight])

  const handleTierChange = ({ pctGood: g, pctBetter: b, pctBest: be }) => {
    setPctGood(g)
    setPctBetter(b)
    setPctBest(be)
  }

  const handleDeleteRoom = async (roomId) => {
    if (!projectId) return
    try {
      const res = await axios.delete(`/api/projects/${projectId}/estimate/rooms/${roomId}`)
      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
    } catch (err) {
      console.error('Failed to delete room:', err)
    }
  }

  const handleAddRoom = async () => {
    if (!projectId) return
    try {
      const res = await axios.post(`/api/projects/${projectId}/estimate/rooms`, {
        name: 'New Room',
        room_type: 'bedroom',
        sqft: 150,
        ceiling_height_ft: ceilingHeight,
      })
      setRooms(res.data.rooms || [])
      setSummary(res.data.summary || null)
    } catch (err) {
      console.error('Failed to add room:', err)
    }
  }

  const handleUpdateRoom = async (updatedRoom) => {
    if (!projectId) return
    const updatedRooms = rooms.map(r => r.id === updatedRoom.id ? updatedRoom : r)
    setRooms(updatedRooms)

    // Debounced full room list update
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await axios.patch(`/api/projects/${projectId}/estimate`, {
          rooms: updatedRooms.map(r => ({
            name: r.name,
            room_type: r.room_type,
            sqft: r.sqft,
            width_ft: r.width_ft,
            length_ft: r.length_ft,
            ceiling_height_ft: r.ceiling_height_ft,
          })),
        })
        setRooms(res.data.rooms || [])
        setSummary(res.data.summary || null)
      } catch (err) {
        console.error('Failed to update rooms:', err)
      }
    }, 600)
  }

  const handleViewResults = () => {
    if (projectId && summary) {
      onComplete(projectId, rooms, summary)
    }
  }

  const fmtCurrency = (n) => {
    if (!n) return '$0'
    return '$' + Math.round(n).toLocaleString()
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Hero */}
      <div className="mb-8">
        <div className="text-[10px] uppercase tracking-[0.28em] text-gold mb-2 font-medium">Estimate Builder</div>
        <h1 className="text-3xl font-light text-charcoal">New Lighting Estimate</h1>
        <p className="text-sm text-gray-500 mt-2 max-w-lg leading-relaxed">
          Enter the home details below. Rooms are auto-generated from square footage, and pricing updates live as you adjust the tier split.
        </p>
      </div>

      {/* Section 1: Project Info */}
      <Section num={1} title="Project Information" subtitle="Name, address, and home profile" complete={!!name && sqft > 0}>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-gold mb-1.5 block font-medium">Project Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Williams Residence"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:border-gold focus:outline-none"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-gold mb-1.5 block font-medium">Address / Lot</label>
            <input
              value={address}
              onChange={e => setAddress(e.target.value)}
              placeholder="e.g. 123 Brookside Lane"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:border-gold focus:outline-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-gold mb-1.5 block font-medium">
              Total Square Footage <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              min={500}
              max={30000}
              step={100}
              value={sqft}
              onChange={e => setSqft(parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:border-gold focus:outline-none text-lg font-light"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-gold mb-1.5 block font-medium">Stories</label>
            <div className="flex border border-gray-300 rounded overflow-hidden">
              {[1, 2, 3].map(n => (
                <button
                  key={n}
                  onClick={() => setStories(n)}
                  className={`flex-1 py-2 text-sm transition-colors ${
                    stories === n
                      ? 'bg-charcoal text-white'
                      : 'bg-white text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-gold mb-1.5 block font-medium">Ceiling Height</label>
            <select
              value={ceilingHeight}
              onChange={e => setCeilingHeight(parseInt(e.target.value))}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:border-gold focus:outline-none"
            >
              {CEILING_HEIGHTS.map(h => (
                <option key={h} value={h}>{h} ft</option>
              ))}
            </select>
          </div>
        </div>

        {!estimateCreated && (
          <div className="mt-5 flex items-center gap-4">
            <button
              onClick={createEstimate}
              disabled={loading || sqft < 500}
              className="px-6 py-2.5 bg-charcoal text-white text-[10px] uppercase tracking-widest rounded hover:bg-charcoal-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading && (
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              {loading ? 'Generating...' : 'Generate Rooms'}
            </button>
            {sqft < 500 && sqft > 0 && (
              <span className="text-xs text-amber-600">Minimum 500 sqft</span>
            )}
          </div>
        )}
        {error && (
          <div className="mt-3 px-4 py-2.5 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {error}
          </div>
        )}
      </Section>

      {/* Section 2: Tier Allocation */}
      {estimateCreated && (
        <Section num={2} title="Tier Allocation" subtitle="Distribute Good / Better / Best across the home" complete={pctGood + pctBetter + pctBest === 100}>
          <TierBar
            pctGood={pctGood}
            pctBetter={pctBetter}
            pctBest={pctBest}
            onChange={handleTierChange}
          />
        </Section>
      )}

      {/* Section 3: Room Breakdown */}
      {estimateCreated && rooms.length > 0 && (
        <Section num={3} title="Room Breakdown" subtitle={`${rooms.length} rooms auto-generated`} complete={rooms.length > 0}>
          <div className="mt-3">
            {/* Header */}
            <div className="flex items-center gap-3 pb-2 border-b border-gray-200 text-[10px] uppercase tracking-wider text-gray-400 font-medium">
              <div className="flex-1">Room</div>
              <div className="w-28">Type</div>
              <div className="w-20 text-right">Sqft</div>
              <div className="w-16 text-center">Tier</div>
              <div className="w-4" />
            </div>

            {/* Rows */}
            {rooms.map((room) => (
              <RoomRow
                key={room.id}
                room={room}
                onUpdate={handleUpdateRoom}
                onDelete={() => handleDeleteRoom(room.id)}
              />
            ))}

            {/* Add room */}
            <button
              onClick={handleAddRoom}
              className="mt-3 text-sm text-gold hover:text-gold-dark transition-colors"
            >
              + Add room
            </button>
          </div>
        </Section>
      )}

      {/* Sticky footer with live total */}
      {estimateCreated && summary && (
        <div className="sticky bottom-0 z-50 bg-white border border-gray-200 rounded-md mt-4 shadow-lg">
          <div className="flex items-center justify-between px-5 py-4">
            <div>
              <div className="text-[9px] uppercase tracking-[0.22em] text-gray-400 mb-1">Estimated Investment</div>
              <div className="text-2xl font-light text-charcoal">
                {fmtCurrency(summary.budget_low)} – {fmtCurrency(summary.budget_high)}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {summary.total_fixtures} fixtures · {rooms.length} rooms
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleViewResults}
                className="px-5 py-2.5 bg-charcoal text-white text-[10px] uppercase tracking-widest rounded hover:bg-charcoal-dark transition-colors"
              >
                View Full Schedule
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
