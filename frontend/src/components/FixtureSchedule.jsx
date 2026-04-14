import { useMemo } from 'react'
import axios from 'axios'

/**
 * Aggregate fixtures by type within each room for display.
 */
function aggregateFixtures(rooms) {
  const result = []

  for (const room of rooms) {
    const groups = {}
    for (const f of room.fixtures || []) {
      const key = f.fixture_type
      if (!groups[key]) {
        groups[key] = {
          type: f.fixture_type,
          qty: 0,
          product: f.product_desc || f.product_sku || '',
          msrp: f.msrp_range || '',
          notes: [],
          isPrewire: f.is_prewire,
        }
      }
      groups[key].qty += 1
      if (f.notes && !groups[key].notes.includes(f.notes)) {
        groups[key].notes.push(f.notes)
      }
    }

    result.push({
      roomName: room.name,
      roomType: room.room_type,
      fixtures: Object.values(groups),
    })
  }

  return result
}

function formatType(type) {
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Parse a msrp range string like "$80-120" or "$80-$120" into [min, max].
 * Returns [0, 0] if the string can't be parsed.
 */
function parseMsrpRange(str) {
  if (!str) return [0, 0]
  const range = str.match(/\$?\s*(\d+(?:\.\d+)?)\s*-\s*\$?\s*(\d+(?:\.\d+)?)/)
  if (range) return [parseFloat(range[1]), parseFloat(range[2])]
  const single = str.match(/\$?\s*(\d+(?:\.\d+)?)/)
  if (single) {
    const v = parseFloat(single[1])
    return [v, v]
  }
  return [0, 0]
}

function formatCurrency(value) {
  return `$${Math.round(value).toLocaleString()}`
}

export default function FixtureSchedule({ rooms, projectId, tier }) {
  const schedule = useMemo(() => aggregateFixtures(rooms), [rooms])

  const totalFixtures = useMemo(() => {
    let count = 0
    for (const room of schedule) {
      for (const f of room.fixtures) {
        count += f.qty
      }
    }
    return count
  }, [schedule])

  const totalBudget = useMemo(() => {
    let min = 0
    let max = 0
    for (const room of schedule) {
      for (const f of room.fixtures) {
        const [lo, hi] = parseMsrpRange(f.msrp)
        min += lo * f.qty
        max += hi * f.qty
      }
    }
    return { min, max }
  }, [schedule])

  const handleExportPdf = async () => {
    if (!projectId) return
    try {
      const res = await axios.get(`/api/exports/projects/${projectId}/pdf`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `LightPlan_${projectId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF export failed:', err)
      alert('Failed to generate PDF. Please try again.')
    }
  }

  if (!rooms || rooms.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        No rooms to display. Upload a floor plan to get started.
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header bar */}
      <div className="bg-charcoal px-6 py-4 flex items-center justify-between">
        <div>
          <h3 className="text-white font-semibold">Fixture Schedule</h3>
          <p className="text-gray-400 text-sm">
            {rooms.length} rooms, {totalFixtures} fixtures
          </p>
        </div>
        <button
          onClick={handleExportPdf}
          className="bg-gold hover:bg-gold-dark text-charcoal font-semibold px-5 py-2 rounded-md transition-colors text-sm"
        >
          Download PDF
        </button>
      </div>

      {/* Table */}
      <div className="fixture-table-wrap overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-gold bg-gray-50">
              <th className="text-left px-4 py-3 font-semibold text-charcoal">Room</th>
              <th className="text-left px-4 py-3 font-semibold text-charcoal">Fixture Type</th>
              <th className="text-center px-4 py-3 font-semibold text-charcoal">Qty</th>
              <th className="text-left px-4 py-3 font-semibold text-charcoal">Product</th>
              <th className="text-left px-4 py-3 font-semibold text-charcoal">Budget Range</th>
              <th className="text-left px-4 py-3 font-semibold text-charcoal">Notes</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((room, ri) =>
              room.fixtures.map((f, fi) => (
                <tr
                  key={`${ri}-${fi}`}
                  className={`border-b border-gray-100 ${ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}
                >
                  <td className="px-4 py-2.5 font-medium text-charcoal">
                    {fi === 0 ? room.roomName : ''}
                  </td>
                  <td className="px-4 py-2.5">
                    {formatType(f.type)}
                    {f.isPrewire && (
                      <span className="ml-2 text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">
                        pre-wire
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-center">{f.qty}</td>
                  <td className="px-4 py-2.5 text-gray-600">{f.product}</td>
                  <td className="px-4 py-2.5 text-gray-600">{f.msrp}</td>
                  <td className="px-4 py-2.5 text-gray-500 text-xs">
                    {f.notes.join('; ')}
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {totalBudget.max > 0 && (
            <tfoot>
              <tr className="border-t-2 border-gold bg-gray-50">
                <td
                  colSpan={4}
                  className="px-4 py-3 text-right font-semibold text-charcoal uppercase text-xs tracking-wide"
                >
                  Total Budget Range
                </td>
                <td className="px-4 py-3 font-semibold text-charcoal whitespace-nowrap">
                  {formatCurrency(totalBudget.min)} – {formatCurrency(totalBudget.max)}
                </td>
                <td className="px-4 py-3"></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Footer */}
      <div className="px-6 py-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-500 italic">
        This layout is dimming-ready. Ask your Livewire rep about Lutron integration options.
      </div>
    </div>
  )
}
