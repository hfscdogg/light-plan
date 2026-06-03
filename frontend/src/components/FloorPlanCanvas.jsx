import { useState, useMemo, useRef, useEffect } from 'react'

// Room types excluded from the overlay — too small or out of scope
const SKIP_ROOM_TYPES = new Set([
  'closet', 'walk_in_closet', 'pantry', 'other',
  'garage', 'porch', 'patio', 'mudroom',
])

// Fixture types rendered on the overlay
const OVERLAY_TYPES = new Set([
  'recessed', 'pendant', 'sconce', 'ceiling_fan',
  'coach_light', 'exhaust_fan',
])

// DMF-style red for all fixture symbols — clean, professional, single color
const FIXTURE_COLOR = '#cc2222'
const LABEL_BG = 'rgba(255,255,255,0.92)'

const clamp01 = v => Math.max(0, Math.min(1, v))
const pct = v => `${clamp01(v) * 100}%`

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
        x: clamp01(f.plan_x),
        y: clamp01(f.plan_y),
      })
    }

    // Label at bbox center — unobtrusive, like DMF's room name placement
    const hasBbox =
      room.bbox_x1 != null && room.bbox_x2 != null &&
      room.bbox_y1 != null && room.bbox_y2 != null

    if (hasBbox) {
      labels.push({
        roomName: room.name,
        x: clamp01((room.bbox_x1 + room.bbox_x2) / 2),
        y: clamp01((room.bbox_y1 + room.bbox_y2) / 2),
      })
    }
  }

  return { markers, labels }
}

function FixtureIcon({ type, size = 14 }) {
  const c = FIXTURE_COLOR
  const sw = 1.4
  switch (type) {
    case 'recessed':
      // DMF style: crosshair/target symbol
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <circle cx="8" cy="8" r="5.5" fill="white" stroke={c} strokeWidth={sw} />
          <line x1="8" y1="1.5" x2="8" y2="5" stroke={c} strokeWidth={sw} />
          <line x1="8" y1="11" x2="8" y2="14.5" stroke={c} strokeWidth={sw} />
          <line x1="1.5" y1="8" x2="5" y2="8" stroke={c} strokeWidth={sw} />
          <line x1="11" y1="8" x2="14.5" y2="8" stroke={c} strokeWidth={sw} />
          <circle cx="8" cy="8" r="1" fill={c} />
        </svg>
      )
    case 'ceiling_fan':
      // Circle with X — fan blades
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <circle cx="8" cy="8" r="6" fill="white" stroke={c} strokeWidth={sw} />
          <line x1="3.5" y1="3.5" x2="12.5" y2="12.5" stroke={c} strokeWidth={sw} />
          <line x1="12.5" y1="3.5" x2="3.5" y2="12.5" stroke={c} strokeWidth={sw} />
          <circle cx="8" cy="8" r="1.2" fill={c} />
        </svg>
      )
    case 'pendant':
      // Filled circle — prominent
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <circle cx="8" cy="8" r="5.5" fill="white" stroke={c} strokeWidth={sw} />
          <circle cx="8" cy="8" r="3" fill={c} />
        </svg>
      )
    case 'sconce':
      // Half-circle against wall — D shape
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <path d="M 8 2 A 6 6 0 0 1 8 14" fill="white" stroke={c} strokeWidth={sw} />
          <line x1="8" y1="2" x2="8" y2="14" stroke={c} strokeWidth={sw} />
        </svg>
      )
    case 'exhaust_fan':
      // Square with cross
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <rect x="2" y="2" width="12" height="12" fill="white" stroke={c} strokeWidth={sw} rx="1" />
          <line x1="5" y1="8" x2="11" y2="8" stroke={c} strokeWidth={1.2} />
          <line x1="8" y1="5" x2="8" y2="11" stroke={c} strokeWidth={1.2} />
        </svg>
      )
    case 'coach_light':
      // Diamond
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <polygon points="8,1.5 14.5,8 8,14.5 1.5,8" fill="white" stroke={c} strokeWidth={sw} />
          <circle cx="8" cy="8" r="1.5" fill={c} />
        </svg>
      )
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 16 16" className="block">
          <circle cx="8" cy="8" r="5.5" fill="white" stroke={c} strokeWidth={sw} />
        </svg>
      )
  }
}

function Legend({ iconSize }) {
  const items = [
    { type: 'recessed', label: 'Recessed' },
    { type: 'ceiling_fan', label: 'Fan' },
    { type: 'sconce', label: 'Sconce' },
    { type: 'pendant', label: 'Pendant' },
    { type: 'coach_light', label: 'Coach' },
    { type: 'exhaust_fan', label: 'Exhaust' },
  ]

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2.5 bg-white border-t border-gray-200">
      {items.map(item => (
        <div key={item.type} className="flex items-center gap-1.5">
          <FixtureIcon type={item.type} size={iconSize} />
          <span className="text-gray-500 text-[11px] font-medium tracking-wide uppercase">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

export default function FloorPlanCanvas({ imageUrl, rooms }) {
  const [hovered, setHovered] = useState(null)
  const imgRef = useRef(null)
  const [iconSize, setIconSize] = useState(16)

  useEffect(() => {
    const el = imgRef.current
    if (!el) return

    const update = () => {
      const w = el.clientWidth
      if (w > 0) {
        setIconSize(Math.max(14, Math.min(24, Math.round(w * 0.025))))
      }
    }

    update()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const ro = new ResizeObserver(update)
    ro.observe(el)
    const onLoad = () => update()
    el.addEventListener('load', onLoad)
    return () => {
      ro.disconnect()
      el.removeEventListener('load', onLoad)
    }
  }, [imageUrl])

  const { markers, labels } = useMemo(() => computeOverlay(rooms), [rooms])

  const totalFixtures = useMemo(() => {
    if (!rooms) return 0
    return rooms.reduce((sum, r) => sum + (r.fixtures?.length || 0), 0)
  }, [rooms])

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
      <div className="bg-charcoal-light px-4 py-2 flex items-center justify-between">
        <h3 className="text-white text-sm font-medium tracking-wide">Lighting Layout</h3>
        {totalFixtures > 0 && (
          <span className="text-gray-400 text-xs">{totalFixtures} fixtures total</span>
        )}
      </div>

      <div className="p-1.5 bg-gray-50">
        {imageUrl ? (
          <div className="relative select-none">
            <img
              ref={imgRef}
              src={imageUrl}
              alt="Floor plan"
              className="block w-full h-auto"
              draggable={false}
            />

            <div className="absolute inset-0">
              {/* Fixture icons */}
              {markers.map((m, i) => (
                <div
                  key={`${m.id || i}-${m.type}`}
                  className="absolute pointer-events-auto cursor-pointer"
                  style={{
                    left: pct(m.x),
                    top: pct(m.y),
                    transform: 'translate(-50%, -50%)',
                    zIndex: 10,
                    lineHeight: 0,
                  }}
                  onMouseEnter={() => setHovered(m)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <FixtureIcon type={m.type} size={iconSize} />
                </div>
              ))}

              {/* Room labels — subtle, centered in room, no border box */}
              {labels.map(label => (
                <div
                  key={`label-${label.roomName}`}
                  className="absolute pointer-events-none"
                  style={{
                    left: pct(label.x),
                    top: pct(label.y),
                    transform: 'translate(-50%, -50%)',
                    zIndex: 5,
                  }}
                >
                  <div
                    className="text-[9px] font-bold uppercase tracking-wider text-gray-500 whitespace-nowrap"
                    style={{
                      background: LABEL_BG,
                      padding: '1px 4px',
                      borderRadius: '2px',
                    }}
                  >
                    {label.roomName}
                  </div>
                </div>
              ))}

              {/* Hover tooltip */}
              {hovered && (() => {
                const flipBelow = hovered.y < 0.1
                return (
                  <div
                    className="absolute z-30 bg-gray-900 text-white text-[10px] rounded px-2 py-1 shadow-lg pointer-events-none whitespace-nowrap"
                    style={{
                      left: pct(hovered.x),
                      top: pct(hovered.y),
                      transform: flipBelow
                        ? 'translate(-50%, calc(100% + 6px))'
                        : 'translate(-50%, calc(-100% - 6px))',
                    }}
                  >
                    <span className="font-semibold">{hovered.roomName}</span>
                    <span className="text-gray-400"> · </span>
                    <span className="text-gray-300">{hovered.type.replace(/_/g, ' ')}</span>
                  </div>
                )
              })()}
            </div>
          </div>
        ) : (
          <div className="aspect-[4/3] bg-gray-100 rounded flex items-center justify-center">
            <div className="text-center text-gray-400">
              <p className="text-sm">Upload a floor plan to see lighting layout</p>
            </div>
          </div>
        )}
      </div>

      {markers.length > 0 && <Legend iconSize={Math.max(12, iconSize - 2)} />}
    </div>
  )
}
