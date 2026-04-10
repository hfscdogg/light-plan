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
 * If a room has bounding box data (bbox_x1/y1/x2/y2), fixtures are placed
 * directly within those plan-space boundaries. Otherwise falls back to
 * estimating room extent from center + dimensions.
 */
function computeFixturePositions(rooms) {
  if (!rooms || rooms.length === 0) return []

  const fixtures = []

  for (const room of rooms) {
    const hasBbox = room.bbox_x1 != null && room.bbox_y1 != null
                 && room.bbox_x2 != null && room.bbox_y2 != null

    let roomLeft, roomTop, roomWidth, roomHeight

    if (hasBbox) {
      // Use precise bounding box from Claude Vision
      roomLeft = room.bbox_x1
      roomTop = room.bbox_y1
      roomWidth = room.bbox_x2 - room.bbox_x1
      roomHeight = room.bbox_y2 - room.bbox_y1
    } else {
      // Fallback: estimate from center point (less accurate)
      const cx = room.position_x ?? 0.5
      const cy = room.position_y ?? 0.5
      const fallbackSpan = 0.12
      roomLeft = cx - fallbackSpan / 2
      roomTop = cy - fallbackSpan / 2
      roomWidth = fallbackSpan
      roomHeight = fallbackSpan
    }

    // Small inset so dots don't land exactly on walls
    const inset = 0.05
    const innerLeft = roomLeft + roomWidth * inset
    const innerTop = roomTop + roomHeight * inset
    const innerW = roomWidth * (1 - 2 * inset)
    const innerH = roomHeight * (1 - 2 * inset)

    for (const f of (room.fixtures || [])) {
      // Prefer plan_x/plan_y from Claude pass 2 (precise placement)
      // Fall back to computing from room bbox + fixture room-relative position
      let px, py
      if (f.plan_x != null && f.plan_y != null) {
        px = f.plan_x
        py = f.plan_y
      } else {
        px = innerLeft + f.position_x * innerW
        py = innerTop + f.position_y * innerH
      }

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
