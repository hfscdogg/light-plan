import { useState, useMemo, useRef } from 'react'

/**
 * Floor plan viewer with room-level fixture summary badges.
 *
 * Instead of placing individual fixture symbols (which requires precise
 * room boundary data), shows a single compact badge per room centered
 * on the room's position. Each badge summarizes the fixture counts.
 * Clean, professional, impossible to look "off."
 */

/**
 * Summarize fixtures for each room into badge data.
 */
function computeRoomBadges(rooms) {
  if (!rooms || rooms.length === 0) return []

  const badges = []

  for (const room of rooms) {
    const cx = room.position_x
    const cy = room.position_y
    if (cx == null || cy == null) continue

    const fixtures = room.fixtures || []
    if (fixtures.length === 0) continue

    // Count by type
    const counts = {}
    for (const f of fixtures) {
      counts[f.fixture_type] = (counts[f.fixture_type] || 0) + 1
    }

    // Build badge items (ordered by visual importance)
    const items = []
    if (counts.recessed) items.push({ type: 'recessed', count: counts.recessed })
    if (counts.pendant) items.push({ type: 'pendant', count: counts.pendant })
    if (counts.sconce) items.push({ type: 'sconce', count: counts.sconce })
    if (counts.ceiling_fan) items.push({ type: 'ceiling_fan', count: counts.ceiling_fan })
    if (counts.coach_light) items.push({ type: 'coach_light', count: counts.coach_light })
    if (counts.exhaust_fan) items.push({ type: 'exhaust_fan', count: counts.exhaust_fan })

    badges.push({
      roomName: room.name,
      roomType: room.room_type,
      x: cx,
      y: cy,
      items,
      totalFixtures: fixtures.length,
    })
  }

  return badges
}

/**
 * Tiny inline SVG icon for each fixture type.
 */
function FixtureIcon({ type, size = 10 }) {
  switch (type) {
    case 'recessed':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <circle cx="6" cy="6" r="4.5" fill="none" stroke="#444" strokeWidth="1.5" />
        </svg>
      )
    case 'ceiling_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <circle cx="6" cy="6" r="4.5" fill="none" stroke="#16a34a" strokeWidth="1.5" />
          <line x1="3" y1="3" x2="9" y2="9" stroke="#16a34a" strokeWidth="1" />
          <line x1="9" y1="3" x2="3" y2="9" stroke="#16a34a" strokeWidth="1" />
        </svg>
      )
    case 'pendant':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <circle cx="6" cy="6" r="4.5" fill="none" stroke="#d97706" strokeWidth="1.5" />
          <circle cx="6" cy="6" r="1.5" fill="#d97706" />
        </svg>
      )
    case 'sconce':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <path d="M 6 1.5 A 4.5 4.5 0 0 1 6 10.5" fill="none" stroke="#7c3aed" strokeWidth="1.5" />
          <line x1="6" y1="1.5" x2="6" y2="10.5" stroke="#7c3aed" strokeWidth="1" />
        </svg>
      )
    case 'exhaust_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="#64748b" strokeWidth="1.5" rx="1" />
        </svg>
      )
    case 'coach_light':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <polygon points="6,1 11,6 6,11 1,6" fill="none" stroke="#ca8a04" strokeWidth="1.5" />
        </svg>
      )
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="inline-block">
          <circle cx="6" cy="6" r="4.5" fill="none" stroke="#444" strokeWidth="1.5" />
        </svg>
      )
  }
}

function RoomBadge({ badge, onTap, isSelected }) {
  return (
    <div
      className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer"
      style={{
        left: `${badge.x * 100}%`,
        top: `${badge.y * 100}%`,
        zIndex: isSelected ? 20 : 10,
      }}
      onClick={(e) => { e.stopPropagation(); onTap(badge) }}
    >
      <div
        className={`
          flex items-center gap-1 px-1.5 py-0.5 rounded
          text-[9px] font-medium whitespace-nowrap
          transition-shadow
          ${isSelected
            ? 'bg-white border-2 border-gold shadow-lg'
            : 'bg-white/90 border border-gray-400 shadow-sm hover:shadow-md hover:border-gray-600'
          }
        `}
      >
        {badge.items.slice(0, 3).map((item, i) => (
          <span key={i} className="flex items-center gap-[2px]">
            <span className="text-gray-700">{item.count}</span>
            <FixtureIcon type={item.type} size={9} />
          </span>
        ))}
      </div>
    </div>
  )
}

function Legend() {
  const items = [
    { type: 'recessed', label: 'Recessed' },
    { type: 'ceiling_fan', label: 'Fan' },
    { type: 'sconce', label: 'Sconce' },
    { type: 'pendant', label: 'Pendant' },
    { type: 'coach_light', label: 'Coach' },
    { type: 'exhaust_fan', label: 'Exhaust' },
  ]

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs">
      {items.map(item => (
        <div key={item.type} className="flex items-center gap-1">
          <FixtureIcon type={item.type} size={10} />
          <span className="text-gray-600">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

export default function FloorPlanCanvas({ imageUrl, rooms }) {
  const [selected, setSelected] = useState(null)
  const containerRef = useRef(null)

  const badges = useMemo(() => computeRoomBadges(rooms), [rooms])

  const totalFixtures = useMemo(() => {
    if (!rooms) return 0
    return rooms.reduce((sum, r) => sum + (r.fixtures?.length || 0), 0)
  }, [rooms])

  const handleTap = (badge) => {
    setSelected(prev => prev?.roomName === badge.roomName ? null : badge)
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

            {/* Room fixture badges */}
            <div className="absolute inset-0">
              {badges.map(b => (
                <RoomBadge
                  key={b.roomName}
                  badge={b}
                  onTap={handleTap}
                  isSelected={selected?.roomName === b.roomName}
                />
              ))}
            </div>

            {/* Detail popup for selected room */}
            {selected && (
              <div
                className="absolute z-30 bg-charcoal text-white text-xs rounded-lg px-3 py-2.5 shadow-lg pointer-events-none max-w-[220px]"
                style={{
                  left: `${selected.x * 100}%`,
                  top: `${selected.y * 100}%`,
                  transform: selected.y < 0.3
                    ? 'translate(-50%, 20px)'
                    : 'translate(-50%, calc(-100% - 20px))',
                }}
              >
                <div className="font-semibold text-gold mb-1">{selected.roomName}</div>
                {selected.items.map((item, i) => (
                  <div key={i} className="flex items-center gap-2 py-0.5">
                    <FixtureIcon type={item.type} size={10} />
                    <span className="text-gray-300">
                      {item.count}x {item.type.replace(/_/g, ' ')}
                    </span>
                  </div>
                ))}
                <div className="text-gray-500 mt-1 text-[10px]">
                  {selected.totalFixtures} fixtures total
                </div>
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
      {badges.length > 0 && <Legend />}
    </div>
  )
}
