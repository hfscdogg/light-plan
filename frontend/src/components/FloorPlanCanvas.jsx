import { useState, useMemo, useRef } from 'react'

/**
 * Floor plan viewer that places individual fixture icons on top of the
 * uploaded plan image.
 *
 * Each fixture has server-computed (plan_x, plan_y) coordinates that are
 * clamped inside the room's bounding box in placement.py, so we simply
 * render a small icon at that point. Rooms get a compact label anchored
 * near the top of their fixture cluster so the user can still see which
 * room is which.
 */

// Room types to skip on the overlay (too small or clutter-prone)
const SKIP_ROOM_TYPES = new Set([
  'closet', 'walk_in_closet', 'pantry', 'other',
])

// Fixture types we actually render on the layout
const OVERLAY_TYPES = new Set([
  'recessed', 'pendant', 'sconce', 'ceiling_fan',
  'coach_light', 'exhaust_fan',
])

/**
 * Color per fixture type — matches the legend.
 */
const TYPE_COLORS = {
  recessed: '#444444',
  pendant: '#d97706',
  sconce: '#7c3aed',
  ceiling_fan: '#16a34a',
  coach_light: '#ca8a04',
  exhaust_fan: '#64748b',
}

/**
 * Flatten rooms into a list of fixture markers with absolute plan
 * coordinates. Also returns per-room label anchors so we can place a
 * compact tag next to each room's fixtures.
 */
function computeOverlay(rooms) {
  if (!rooms || rooms.length === 0) return { markers: [], labels: [] }

  const markers = []
  const labels = []

  for (const room of rooms) {
    if (SKIP_ROOM_TYPES.has(room.room_type)) continue

    const fixtures = (room.fixtures || []).filter(f =>
      OVERLAY_TYPES.has(f.fixture_type) &&
      f.plan_x != null &&
      f.plan_y != null
    )
    if (fixtures.length === 0) continue

    for (const f of fixtures) {
      markers.push({
        id: f.id,
        roomName: room.name,
        type: f.fixture_type,
        x: f.plan_x,
        y: f.plan_y,
      })
    }

    // Label anchor: top-most fixture in the cluster. This keeps the label
    // glued to where the fixtures actually render, so if Claude's bbox is
    // off the label drifts with it instead of landing somewhere random.
    const topFixture = fixtures.reduce((best, f) =>
      f.plan_y < best.plan_y ? f : best
    , fixtures[0])

    labels.push({
      roomName: room.name,
      x: topFixture.plan_x,
      y: topFixture.plan_y,
      count: fixtures.length,
    })
  }

  return { markers, labels }
}

/**
 * Tiny inline SVG icon for each fixture type. Rendered centered on the
 * marker coordinate via CSS transforms.
 */
function FixtureIcon({ type, size = 14 }) {
  const color = TYPE_COLORS[type] || '#444444'
  switch (type) {
    case 'recessed':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="1" fill={color} />
        </svg>
      )
    case 'ceiling_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <line x1="2.5" y1="2.5" x2="9.5" y2="9.5" stroke={color} strokeWidth="1.2" />
          <line x1="9.5" y1="2.5" x2="2.5" y2="9.5" stroke={color} strokeWidth="1.2" />
        </svg>
      )
    case 'pendant':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="2" fill={color} />
        </svg>
      )
    case 'sconce':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <path d="M 6 1 A 5 5 0 0 1 6 11" fill="white" stroke={color} strokeWidth="1.5" />
          <line x1="6" y1="1" x2="6" y2="11" stroke={color} strokeWidth="1.5" />
        </svg>
      )
    case 'exhaust_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <rect x="1" y="1" width="10" height="10" fill="white" stroke={color} strokeWidth="1.5" rx="1.5" />
          <line x1="3" y1="6" x2="9" y2="6" stroke={color} strokeWidth="1.2" />
          <line x1="6" y1="3" x2="6" y2="9" stroke={color} strokeWidth="1.2" />
        </svg>
      )
    case 'coach_light':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <polygon points="6,1 11,6 6,11 1,6" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="1.2" fill={color} />
        </svg>
      )
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
        </svg>
      )
  }
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
          <FixtureIcon type={item.type} size={12} />
          <span className="text-gray-600">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

export default function FloorPlanCanvas({ imageUrl, rooms }) {
  const [hovered, setHovered] = useState(null)
  const containerRef = useRef(null)

  const { markers, labels } = useMemo(() => computeOverlay(rooms), [rooms])

  const totalFixtures = useMemo(() => {
    if (!rooms) return 0
    return rooms.reduce((sum, r) => sum + (r.fixtures?.length || 0), 0)
  }, [rooms])

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
          <div ref={containerRef} className="relative select-none">
            <img
              src={imageUrl}
              alt="Uploaded floor plan"
              className="w-full h-auto rounded border border-gray-200"
              draggable={false}
            />

            {/* Fixture icons */}
            <div className="absolute inset-0 pointer-events-none">
              {markers.map((m, i) => (
                <div
                  key={`${m.id || i}-${m.type}`}
                  className="absolute pointer-events-auto cursor-pointer"
                  style={{
                    left: `${m.x * 100}%`,
                    top: `${m.y * 100}%`,
                    transform: 'translate(-50%, -50%)',
                    zIndex: 10,
                  }}
                  onMouseEnter={() => setHovered(m)}
                  onMouseLeave={() => setHovered(null)}
                  title={`${m.roomName} — ${m.type.replace(/_/g, ' ')}`}
                >
                  <FixtureIcon type={m.type} size={14} />
                </div>
              ))}

              {/* Compact room tag anchored just above the top fixture */}
              {labels.map(label => (
                <div
                  key={`label-${label.roomName}`}
                  className="absolute"
                  style={{
                    left: `${label.x * 100}%`,
                    top: `${label.y * 100}%`,
                    transform: 'translate(-50%, calc(-100% - 12px))',
                    zIndex: 20,
                  }}
                >
                  <div className="bg-white/90 border border-gray-300 rounded px-1.5 py-[1px] text-[8px] font-semibold text-charcoal whitespace-nowrap shadow-sm">
                    {label.roomName}
                  </div>
                </div>
              ))}

              {/* Hover tooltip */}
              {hovered && (
                <div
                  className="absolute z-30 bg-charcoal text-white text-[10px] rounded px-2 py-1 shadow-lg pointer-events-none whitespace-nowrap"
                  style={{
                    left: `${hovered.x * 100}%`,
                    top: `${hovered.y * 100}%`,
                    transform: 'translate(-50%, calc(-100% - 18px))',
                  }}
                >
                  <span className="text-gold font-semibold">{hovered.roomName}</span>
                  <span className="text-gray-300"> · {hovered.type.replace(/_/g, ' ')}</span>
                </div>
              )}
            </div>
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
      {markers.length > 0 && <Legend />}
    </div>
  )
}
