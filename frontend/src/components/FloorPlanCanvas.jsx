import { useState, useMemo, useRef, useEffect } from 'react'

/**
 * Floor plan viewer with fixture overlay.
 *
 * Renders colored dots on top of the uploaded plan image at each
 * fixture's position. Positions are computed from room centers
 * (0-1 on plan) and fixture offsets (0-1 within room).
 */

const FIXTURE_STYLES = {
  recessed:        { color: '#3B82F6', label: 'Recessed' },
  pendant:         { color: '#F59E0B', label: 'Pendant' },
  sconce:          { color: '#8B5CF6', label: 'Sconce' },
  ceiling_fan:     { color: '#10B981', label: 'Ceiling Fan' },
  switched_outlet: { color: '#78716C', label: 'Switched Outlet' },
  exhaust_fan:     { color: '#64748B', label: 'Exhaust Fan' },
  coach_light:     { color: '#EAB308', label: 'Coach Light' },
  landscape:       { color: '#84CC16', label: 'Landscape' },
  under_cabinet:   { color: '#EC4899', label: 'Under Cabinet' },
}

function getFixtureStyle(type) {
  return FIXTURE_STYLES[type] || { color: '#EF4444', label: type.replace(/_/g, ' ') }
}

/**
 * Compute plan-level (x, y) for each fixture.
 *
 * Each room has a center (position_x, position_y) on the overall plan (0-1).
 * Each fixture has a position (0-1) within that room.
 * We estimate how much plan-space each room occupies from its ft dimensions
 * relative to the total plan, then map fixture positions into plan coords.
 */
function computeFixturePositions(rooms) {
  if (!rooms || rooms.length === 0) return []

  // Estimate plan dimensions from room position spread + sizes.
  // Use the bounding box of room centers to gauge how big the plan is,
  // then size each room relative to that.
  let minX = 1, maxX = 0, minY = 1, maxY = 0
  let maxRoomW = 0, maxRoomL = 0
  for (const r of rooms) {
    const cx = r.position_x ?? 0.5
    const cy = r.position_y ?? 0.5
    if (cx < minX) minX = cx
    if (cx > maxX) maxX = cx
    if (cy < minY) minY = cy
    if (cy > maxY) maxY = cy
    if ((r.width_ft || 0) > maxRoomW) maxRoomW = r.width_ft || 12
    if ((r.length_ft || 0) > maxRoomL) maxRoomL = r.length_ft || 12
  }

  // Plan spread in coordinate space (how far apart room centers are)
  const spreadX = Math.max(0.3, maxX - minX)
  const spreadY = Math.max(0.3, maxY - minY)

  // Estimate how many "room widths" fit across the plan
  const avgRoomW = rooms.reduce((s, r) => s + (r.width_ft || 12), 0) / rooms.length
  const avgRoomL = rooms.reduce((s, r) => s + (r.length_ft || 12), 0) / rooms.length
  const roomCountX = Math.max(2, Math.round(Math.sqrt(rooms.length) * 1.3))
  const roomCountY = Math.max(2, Math.round(Math.sqrt(rooms.length)))

  const fixtures = []

  for (const room of rooms) {
    const cx = room.position_x ?? 0.5
    const cy = room.position_y ?? 0.5
    const rw = room.width_ft || 12
    const rl = room.length_ft || 12

    // Each room gets a fraction of the plan space.
    // Scale tightly so fixtures stay inside room boundaries.
    const spanX = (spreadX / roomCountX) * (rw / avgRoomW) * 0.7
    const spanY = (spreadY / roomCountY) * (rl / avgRoomL) * 0.7

    for (const f of (room.fixtures || [])) {
      // Map fixture's room-relative position to plan position
      const px = cx + (f.position_x - 0.5) * spanX
      const py = cy + (f.position_y - 0.5) * spanY

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

function FixtureDot({ fixture, onTap, isSelected }) {
  const style = getFixtureStyle(fixture.type)
  const size = fixture.isPrewire ? 8 : 10

  return (
    <div
      className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-transform hover:scale-[1.8]"
      style={{
        left: `${fixture.x * 100}%`,
        top: `${fixture.y * 100}%`,
        zIndex: isSelected ? 20 : 10,
      }}
      onClick={(e) => { e.stopPropagation(); onTap(fixture) }}
    >
      <div
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          backgroundColor: fixture.isPrewire ? 'white' : style.color,
          border: `2px solid ${style.color}`,
          boxShadow: isSelected
            ? `0 0 0 3px ${style.color}50, 0 1px 3px rgba(0,0,0,0.4)`
            : '0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.5)',
        }}
      />
    </div>
  )
}

function Legend({ visibleTypes }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs">
      {visibleTypes.map(type => {
        const style = getFixtureStyle(type)
        return (
          <div key={type} className="flex items-center gap-1">
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: style.color,
              }}
            />
            <span className="text-gray-600">{style.label}</span>
          </div>
        )
      })}
      <div className="flex items-center gap-1">
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: 'transparent',
            border: '2px solid #999',
          }}
        />
        <span className="text-gray-600">Pre-wire</span>
      </div>
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
    return [...types].sort()
  }, [fixturePositions])

  const handleTap = (fixture) => {
    setSelected(prev => prev?.id === fixture.id ? null : fixture)
  }

  const handleBackgroundClick = () => {
    setSelected(null)
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-charcoal-light px-4 py-2 flex items-center justify-between">
        <h3 className="text-white text-sm font-medium">Floor Plan</h3>
        {fixturePositions.length > 0 && (
          <span className="text-gray-400 text-xs">{fixturePositions.length} fixtures</span>
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

            {/* Fixture dots overlay */}
            <div className="absolute inset-0">
              {fixturePositions.map(f => (
                <FixtureDot
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
                    ? 'translate(-50%, 12px)'
                    : 'translate(-50%, calc(-100% - 12px))',
                }}
              >
                <div className="font-semibold" style={{ color: getFixtureStyle(selected.type).color }}>
                  {getFixtureStyle(selected.type).label}
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
              <p className="text-sm">Upload a floor plan to see fixture layout</p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      {visibleTypes.length > 0 && <Legend visibleTypes={visibleTypes} />}
    </div>
  )
}
