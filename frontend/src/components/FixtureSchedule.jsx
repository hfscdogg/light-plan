import { useMemo } from 'react'
import axios from 'axios'

function aggregateFixtures(rooms) {
  const result = []
  for (const room of rooms) {
    const groups = {}
    for (const f of room.fixtures || []) {
      const key = f.fixture_type
      if (!groups[key]) {
        groups[key] = { type: f.fixture_type, qty: 0, product: f.product_desc || f.product_sku || '', msrp: f.msrp_range || '', notes: [], isPrewire: f.is_prewire }
      }
      groups[key].qty += 1
      if (f.notes && !groups[key].notes.includes(f.notes)) groups[key].notes.push(f.notes)
    }
    result.push({ roomName: room.name, roomType: room.room_type, fixtures: Object.values(groups) })
  }
  return result
}

function formatType(t) { return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }

function parseMsrpRange(str) {
  if (!str) return [0, 0]
  const r = str.match(/\$?\s*(\d+(?:\.\d+)?)\s*-\s*\$?\s*(\d+(?:\.\d+)?)/)
  if (r) return [parseFloat(r[1]), parseFloat(r[2])]
  const s = str.match(/\$?\s*(\d+(?:\.\d+)?)/)
  if (s) { const v = parseFloat(s[1]); return [v, v] }
  return [0, 0]
}

const fmt = v => '$' + Math.round(v).toLocaleString()

export default function FixtureSchedule({ rooms, projectId, tier }) {
  const schedule = useMemo(() => aggregateFixtures(rooms), [rooms])
  const totalFixtures = useMemo(() => schedule.reduce((s, r) => s + r.fixtures.reduce((a, f) => a + f.qty, 0), 0), [schedule])
  const totalBudget = useMemo(() => {
    let min = 0, max = 0
    for (const room of schedule) for (const f of room.fixtures) { const [lo, hi] = parseMsrpRange(f.msrp); min += lo * f.qty; max += hi * f.qty }
    return { min, max }
  }, [schedule])

  const handleExportPdf = async () => {
    if (!projectId) return
    try {
      const res = await axios.get(`/api/exports/projects/${projectId}/pdf`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a'); a.href = url; a.download = `LightPlan_${projectId}.pdf`; a.click(); URL.revokeObjectURL(url)
    } catch (err) { console.error('PDF export failed:', err) }
  }

  if (!rooms || rooms.length === 0) {
    return (
      <div className="bg-white border border-bone-300 rounded-md p-10 text-center">
        <div className="font-serif text-xl text-ink-500 font-light italic">No rooms to display</div>
        <p className="text-ink-400 text-sm mt-2">Create an estimate to get started.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-bone-300 rounded-md overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-bone-200 flex items-center justify-between">
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold mb-0.5">Fixture Schedule</div>
          <div className="font-serif text-lg text-ink-800 font-light italic">
            {rooms.length} rooms · {totalFixtures} fixtures
          </div>
        </div>
        <button onClick={handleExportPdf}
          className="px-5 py-2 bg-copper-500 text-white text-[10.5px] uppercase tracking-[0.14em] font-semibold rounded-full hover:bg-copper-600 transition-colors">
          Download PDF
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-bone-300 bg-bone-50">
              <th className="text-left px-5 py-3 text-[9px] uppercase tracking-[0.2em] text-copper-700 font-semibold">Room</th>
              <th className="text-left px-4 py-3 text-[9px] uppercase tracking-[0.2em] text-copper-700 font-semibold">Fixture Type</th>
              <th className="text-center px-3 py-3 text-[9px] uppercase tracking-[0.2em] text-copper-700 font-semibold">Qty</th>
              <th className="text-left px-4 py-3 text-[9px] uppercase tracking-[0.2em] text-copper-700 font-semibold">Product</th>
              <th className="text-right px-5 py-3 text-[9px] uppercase tracking-[0.2em] text-copper-700 font-semibold">Budget</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((room, ri) =>
              room.fixtures.map((f, fi) => (
                <tr key={`${ri}-${fi}`} className="border-b border-bone-100 hover:bg-bone-50/50 transition-colors">
                  <td className="px-5 py-2.5 text-sm text-ink-700 font-medium">{fi === 0 ? room.roomName : ''}</td>
                  <td className="px-4 py-2.5 text-sm text-ink-500">
                    {formatType(f.type)}
                    {f.isPrewire && (
                      <span className="ml-2 text-[9px] uppercase tracking-wider text-copper-700 border border-copper/30 px-1.5 py-0.5 rounded-sm font-semibold">pre-wire</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-center font-serif text-base text-ink-800">{f.qty}</td>
                  <td className="px-4 py-2.5 text-xs text-ink-400">{f.product}</td>
                  <td className="px-5 py-2.5 text-right font-serif text-sm text-ink-500">{f.msrp}</td>
                </tr>
              ))
            )}
          </tbody>
          {totalBudget.max > 0 && (
            <tfoot>
              <tr className="border-t border-bone-300 bg-bone-50">
                <td colSpan={3} className="px-5 py-3 text-right text-[9px] uppercase tracking-[0.2em] text-ink-400 font-semibold">Estimated Range</td>
                <td />
                <td className="px-5 py-3 text-right font-serif text-lg text-ink-800 whitespace-nowrap">
                  {fmt(totalBudget.min)} — {fmt(totalBudget.max)}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      <div className="px-6 py-3 border-t border-bone-200">
        <p className="text-[11px] text-ink-400 italic leading-relaxed">
          This layout is dimming-ready. All pre-wire locations prepared for future fixture installation.
          Contact your Livewire representative about Lutron integration options.
        </p>
      </div>
    </div>
  )
}
