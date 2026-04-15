import { useState, useMemo, useRef, useEffect } from 'react'

/**
 * Floor plan viewer that places individual fixture icons on top of the
 * uploaded plan image.
 *
 * Each fixture has server-computed (plan_x, plan_y) coordinates that are
 * clamped inside the room's bounding box in placement.py, so we render a
 * small SVG icon at that point. Each room also gets a compact label
 * anchored at the top-center of its bounding box so the user can still
 * see which cluster belongs to which room.
 *
 * Responsibilities handled here:
 *   - icons sized proportionally to the image (via ResizeObserver)
 *   - icons and labels visually clamped to the image rect
 *   - labels positioned at bbox top-center, with a below-fall-back for
 *     rooms near the top edge so the label never clips
 *   - hover tooltip that flips to render below an icon near the top edge
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

const clamp01 = v => Math.max(0, Math.min(1, v))
const pct = v => `${clamp01(v) * 100}%`

/**
 * Flatten rooms into a list of fixture markers + per-room labels.
 *
 * Label anchor logic (important):
 *   - If the room has a bounding box, anchor the label at the bbox's
 *     top-center. This is robust regardless of how the fixture grid
 *     inside the room is laid out.
 *   - Otherwise, fall back to the centroid of the fixtures (horizontal
 *     average) paired with the topmost fixture y.
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
        x: clamp01(f.plan_x),
        y: clamp01(f.plan_y),
      })
    }

    const hasBbox =
      room.bbox_x1 != null && room.bbox_x2 != null &&
      room.bbox_y1 != null && room.bbox_y2 != null

    let labelX
    let labelY
    if (hasBbox) {
      labelX = (room.bbox_x1 + room.bbox_x2) / 2
      labelY = room.bbox_y1
    } else {
      const avgX = fixtures.reduce((s, f) => s + f.plan_x, 0) / fixtures.length
      const minY = fixtures.reduce((m, f) => Math.min(m, f.plan_y), fixtures[0].plan_y)
      labelX = avgX
      labelY = minY
    }

    labels.push({
      roomName: room.name,
      x: clamp01(labelX),
      y: clamp01(labelY),
    })
  }

  return { markers, labels }
}

/**
 * Tiny inline SVG icon for each fixture type. Rendered centered on the
 * marker coordinate via CSS transforms. Size is passed in from the
 * parent so the whole overlay scales with the image.
 */
function FixtureIcon({ type, size = 14 }) {
  const color = TYPE_COLORS[type] || '#444444'
  switch (type) {
    case 'recessed':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="1" fill={color} />
        </svg>
      )
    case 'ceiling_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <line x1="2.5" y1="2.5" x2="9.5" y2="9.5" stroke={color} strokeWidth="1.2" />
          <line x1="9.5" y1="2.5" x2="2.5" y2="9.5" stroke={color} strokeWidth="1.2" />
        </svg>
      )
    case 'pendant':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="2" fill={color} />
        </svg>
      )
    case 'sconce':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <path d="M 6 1 A 5 5 0 0 1 6 11" fill="white" stroke={color} strokeWidth="1.5" />
          <line x1="6" y1="1" x2="6" y2="11" stroke={color} strokeWidth="1.5" />
        </svg>
      )
    case 'exhaust_fan':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <rect x="1" y="1" width="10" height="10" fill="white" stroke={color} strokeWidth="1.5" rx="1.5" />
          <line x1="3" y1="6" x2="9" y2="6" stroke={color} strokeWidth="1.2" />
          <line x1="6" y1="3" x2="6" y2="9" stroke={color} strokeWidth="1.2" />
        </svg>
      )
    case 'coach_light':
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <polygon points="6,1 11,6 6,11 1,6" fill="white" stroke={color} strokeWidth="1.5" />
          <circle cx="6" cy="6" r="1.2" fill={color} />
        </svg>
      )
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 12 12" className="block">
          <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
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
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs">
      {items.map(item => (
        <div key={item.type} className="flex items-center gap-1.5">
          <FixtureIcon type={item.type} size={iconSize} />
          <span className="text-gray-600">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

export default function FloorPlanCanvas({ imageUrl, rooms }) {
  const [hovered, setHovered] = useState(null)
  const containerRef = useRef(null)
  const imgRef = useRef(null)

  // Icon size scales with the rendered image width so icons stay visually
  // proportional across phone / tablet / desktop. 2.2% of image width,
  // clamped to a sensible range.
  const [iconSize, setIconSize] = useState(16)

  useEffect(() => {
    const el = imgRef.current
    if (!el) return

    const update = () => {
      const w = el.clientWidth
      if (w > 0) {
        setIconSize(Math.max(12, Math.min(22, Math.round(w * 0.022))))
      }
    }

    update()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const ro = new ResizeObserver(update)
    ro.observe(el)
    // Also update once the image finishes loading, since clientWidth can
    // be 0 before the natural size is known.
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
              ref={imgRef}
              src={imageUrl}
              alt="Uploaded floor plan"
              className="block w-full h-auto rounded border border-gray-200"
              draggable={false}
            />

            {/* Overlay is sized to exactly match the image rect */}
            <div className="absolute inset-0 pointer-events-none">
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
                  title={`${m.roomName} — ${m.type.replace(/_/g, ' ')}`}
                >
                  <FixtureIcon type={m.type} size={iconSize} />
                </div>
              ))}

              {/* Room name tags anchored at the top-center of each bbox.
                  For rooms sitting in the top 8% of the image we flip the
                  label to render BELOW the anchor so it can't clip above
                  the image edge. */}
              {labels.map(label => {
                const flipBelow = label.y < 0.08
                const transform = flipBelow
                  ? 'translate(-50%, 4px)'
                  : 'translate(-50%, calc(-100% - 4px))'
                return (
                  <div
                    key={`label-${label.roomName}`}
                    className="absolute"
                    style={{
                      left: pct(label.x),
                      top: pct(label.y),
                      transform,
                      zIndex: 20,
                      maxWidth: '70%',
                    }}
                  >
                    <div className="bg-white/85 border border-gray-300 rounded px-1.5 py-[1px] text-[10px] font-semibold text-charcoal shadow-sm leading-tight whitespace-nowrap overflow-hidden text-ellipsis">
                      {label.roomName}
                    </div>
                  </div>
                )
              })}

              {/* Hover tooltip — flipped below when near the top edge */}
              {hovered && (() => {
                const flipBelow = hovered.y < 0.08
                const transform = flipBelow
                  ? 'translate(-50%, calc(100% + 4px))'
                  : 'translate(-50%, calc(-100% - 8px))'
                return (
                  <div
                    className="absolute z-30 bg-charcoal text-white text-[10px] rounded px-2 py-1 shadow-lg pointer-events-none whitespace-nowrap"
                    style={{
                      left: pct(hovered.x),
                      top: pct(hovered.y),
                      transform,
                    }}
                  >
                    <span className="text-gold font-semibold">{hovered.roomName}</span>
                    <span className="text-gray-300"> · {hovered.type.replace(/_/g, ' ')}</span>
                  </div>
                )
              })()}
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
      {markers.length > 0 && <Legend iconSize={Math.max(10, iconSize - 2)} />}
    </div>
  )
}
