import { useState, useMemo, useRef } from 'react'

/**
 * Floor plan viewer with reflected ceiling plan (RCP) style overlay.
 *
 * Uses architectural conventions: open circles for recessed cans,
 * crossed circles for fans, small squares for sconces. Keeps the
 * overlay clean and professional as a conversation starter.
 */

// Max recessed cans to show per room on overlay (full count in schedule)
const MAX_RECESSED_PER_ROOM = 6

// Fixture types to show on overlay
const OVERLAY_TYPES = new Set([
  'recessed', 'pendant', 'sconce', 'ceiling_fan', 'coach_light', 'exhaust_fan',
])

/**
 * Compute plan-level positions for overlay fixtures.
 * Caps recessed cans per room for visual clarity.
 */
function computeFixturePositions(rooms) {
  if (!rooms || rooms.length === 0) return []

  const fixtures = []

  for (const room of rooms) {
    const hasBbox = room.bbox_x1 != null && room.bbox_y1 != null
                 && room.bbox_x2 != null && room.bbox_y2 != null

    let roomLeft, roomTop, roomWidth, roomHeight

    if (hasBbox) {
      roomLeft = room.bbox_x1
      roomTop = room.bbox_y1
      roomWidth = room.bbox_x2 - room.bbox_x1
      roomHeight = room.bbox_y2 - room.bbox_y1
    } else {
      const cx = room.position_x ?? 0.5
      const cy = room.position_y ?? 0.5
      const fallbackSpan = 0.12
      roomLeft = cx - fallbackSpan / 2
      roomTop = cy - fallbackSpan / 2
      roomWidth = fallbackSpan
      roomHeight = fallbackSpan
    }

    // 15% inset from walls
    const inset = 0.15
    const innerLeft = roomLeft + roomWidth * inset
    const innerTop = roomTop + roomHeight * inset
    const innerW = roomWidth * (1 - 2 * inset)
    const innerH = roomHeight * (1 - 2 * inset)

    // Collect overlay fixtures, cap recessed count
    let recessedCount = 0
    const roomFixtures = (room.fixtures || []).filter(f => {
      if (!OVERLAY_TYPES.has(f.fixture_type)) return false
      if (f.fixture_type === 'recessed') {
        recessedCount++
        if (recessedCount > MAX_RECESSED_PER_ROOM) return false
      }
      return true
    })

    for (const f of roomFixtures) {
      const px = innerLeft + f.position_x * innerW
      const py = innerTop + f.position_y * innerH

      fixtures.push({
        id: f.id,
        x: Math.max(0.01, Math.min(0.99, px)),
        y: Math.max(0.01, Math.min(0.99, py)),
        type: f.fixture_type,
        isPrewire: f.is_prewire,
        roomName: room.name,
        notes: f.notes || '',
        product: f.product_desc || '',
      })
    }
  }

  return fixtures
}

/**
 * Architectural fixture symbol rendered as SVG.
 */
function FixtureSymbol({ fixture, onTap, isSelected }) {
  const size = 14

  // Render different shapes per fixture type (RCP conventions)
  const renderSymbol = () => {
    switch (fixture.type) {
      case 'recessed':
        // Open circle (standard RCP recessed can symbol)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="5" fill="white" stroke="#333" strokeWidth="1.5" />
          </svg>
        )
      case 'ceiling_fan':
        // Circle with cross (fan symbol)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="5" fill="white" stroke="#16a34a" strokeWidth="1.5" />
            <line x1="3.5" y1="3.5" x2="10.5" y2="10.5" stroke="#16a34a" strokeWidth="1" />
            <line x1="10.5" y1="3.5" x2="3.5" y2="10.5" stroke="#16a34a" strokeWidth="1" />
          </svg>
        )
      case 'pendant':
        // Filled circle with ring (pendant symbol)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="5" fill="none" stroke="#d97706" strokeWidth="1.5" />
            <circle cx="7" cy="7" r="2" fill="#d97706" />
          </svg>
        )
      case 'sconce':
        // Half circle (wall sconce)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <path d="M 7 2 A 5 5 0 0 1 7 12" fill="none" stroke="#7c3aed" strokeWidth="1.5" />
            <line x1="7" y1="2" x2="7" y2="12" stroke="#7c3aed" strokeWidth="1" />
          </svg>
        )
      case 'exhaust_fan':
        // Square (exhaust/utility symbol)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <rect x="2" y="2" width="10" height="10" fill="white" stroke="#64748b" strokeWidth="1.5" rx="1" />
          </svg>
        )
      case 'coach_light':
        // Diamond (exterior fixture)
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <polygon points="7,1 13,7 7,13 1,7" fill="white" stroke="#ca8a04" strokeWidth="1.5" />
          </svg>
        )
      default:
        return (
          <svg width={size} height={size} viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="5" fill="white" stroke="#333" strokeWidth="1.5" />
          </svg>
        )
    }
  }

  return (
    <div
      className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-transform hover:scale-[1.6]"
      style={{
        left: `${fixture.x * 100}%`,
        top: `${fixture.y * 100}%`,
        zIndex: isSelected ? 20 : 10,
        filter: isSelected ? 'drop-shadow(0 0 4px rgba(0,0,0,0.5))' : 'drop-shadow(0 1px 1px rgba(0,0,0,0.3))',
      }}
      onClick={(e) => { e.stopPropagation(); onTap(fixture) }}
    >
      {renderSymbol()}
    </div>
  )
}

function Legend({ visibleTypes }) {
  const legendItems = [
    { type: 'recessed', label: 'Recessed', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5" fill="white" stroke="#333" strokeWidth="1.5" /></svg>
    )},
    { type: 'ceiling_fan', label: 'Ceiling Fan', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5" fill="white" stroke="#16a34a" strokeWidth="1.5" /><line x1="3.5" y1="3.5" x2="10.5" y2="10.5" stroke="#16a34a" strokeWidth="1" /><line x1="10.5" y1="3.5" x2="3.5" y2="10.5" stroke="#16a34a" strokeWidth="1" /></svg>
    )},
    { type: 'pendant', label: 'Pendant', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5" fill="none" stroke="#d97706" strokeWidth="1.5" /><circle cx="7" cy="7" r="2" fill="#d97706" /></svg>
    )},
    { type: 'sconce', label: 'Sconce', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><path d="M 7 2 A 5 5 0 0 1 7 12" fill="none" stroke="#7c3aed" strokeWidth="1.5" /><line x1="7" y1="2" x2="7" y2="12" stroke="#7c3aed" strokeWidth="1" /></svg>
    )},
    { type: 'exhaust_fan', label: 'Exhaust Fan', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><rect x="2" y="2" width="10" height="10" fill="white" stroke="#64748b" strokeWidth="1.5" rx="1" /></svg>
    )},
    { type: 'coach_light', label: 'Coach Light', symbol: (
      <svg width="12" height="12" viewBox="0 0 14 14"><polygon points="7,1 13,7 7,13 1,7" fill="white" stroke="#ca8a04" strokeWidth="1.5" /></svg>
    )},
  ]

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs">
      {legendItems
        .filter(item => visibleTypes.has(item.type))
        .map(item => (
          <div key={item.type} className="flex items-center gap-1.5">
            {item.symbol}
            <span className="text-gray-600">{item.label}</span>
          </div>
        ))}
    </div>
  )
}

export default function FloorPlanCanvas({ imageUrl, rooms }) {
  const [selected, setSelected] = useState(null)
  const containerRef = useRef(null)

  const fixturePositions = useMemo(() => computeFixturePositions(rooms), [rooms])

  const visibleTypes = useMemo(() => {
    const types = new Set()
    for (const f of fixturePositions) types.add(f.type)
    return types
  }, [fixturePositions])

  const totalFixtures = useMemo(() => {
    if (!rooms) return 0
    return rooms.reduce((sum, r) => sum + (r.fixtures?.length || 0), 0)
  }, [rooms])

  const handleTap = (fixture) => {
    setSelected(prev => prev?.id === fixture.id ? null : fixture)
  }

  const handleBackgroundClick = () => {
    setSelected(null)
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-charcoal-light px-4 py-2 flex items-center justify-between">
        <h3 className="text-white text-sm font-medium">Lighting Layout</h3>
        {totalFixtures > 0 && (
          <span className="text-gray-400 text-xs">{totalFixtures} fixtures total</span>
        )}
      </div>

      <div className="p-2">
        {imageUrl ? (
          <div
            ref={containerRef}
            className="relative select-none"
            onClick={handleBackgroundClick}
          >
            <img
              src={imageUrl}
              alt="Uploaded floor plan"
              className="w-full h-auto rounded border border-gray-200"
              draggable={false}
            />

            {/* RCP-style fixture overlay */}
            <div className="absolute inset-0">
              {fixturePositions.map(f => (
                <FixtureSymbol
                  key={f.id}
                  fixture={f}
                  onTap={handleTap}
                  isSelected={selected?.id === f.id}
                />
              ))}
            </div>

            {/* Tooltip for selected fixture */}
            {selected && (
              <div
                className="absolute z-30 bg-charcoal text-white text-xs rounded-lg px-3 py-2 shadow-lg pointer-events-none max-w-[200px]"
                style={{
                  left: `${selected.x * 100}%`,
                  top: `${selected.y * 100}%`,
                  transform: selected.y < 0.3
                    ? 'translate(-50%, 14px)'
                    : 'translate(-50%, calc(-100% - 14px))',
                }}
              >
                <div className="font-semibold text-gold">
                  {(selected.type || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  {selected.isPrewire && ' (pre-wire)'}
                </div>
                <div className="text-gray-300">{selected.roomName}</div>
                {selected.product && (
                  <div className="text-gray-400 mt-0.5">{selected.product}</div>
                )}
                {selected.notes && (
                  <div className="text-gray-400 mt-0.5">{selected.notes}</div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="aspect-[4/3] bg-gray-100 rounded flex items-center justify-center">
            <div className="text-center text-gray-400">
              <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p className="text-sm">Upload a floor plan to see lighting layout</p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      {visibleTypes.size > 0 && <Legend visibleTypes={visibleTypes} />}
    </div>
  )
}
