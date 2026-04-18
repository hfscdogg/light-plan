import { useState, useMemo } from 'react'

/**
 * SVG schematic diagram of the lighting layout.
 *
 * Renders room rectangles with fixture icons placed at coordinates
 * provided by the backend's schematic_layout field. Falls back to
 * showing the uploaded floor plan image when no schematic data is
 * available.
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
 * Inline SVG fixture icon rendered directly inside the schematic SVG.
 * Each icon is a small <g> translated to the fixture's (x, y) position.
 */
function SvgFixtureIcon({ type, x, y, color }) {
  const c = color || TYPE_COLORS[type] || '#444444'

  switch (type) {
    case 'recessed':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <circle r="6" fill="white" stroke={c} strokeWidth="1.5" />
          <circle r="1.5" fill={c} />
        </g>
      )
    case 'ceiling_fan':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <circle r="7" fill="white" stroke={c} strokeWidth="1.5" />
          <line x1="-4" y1="-4" x2="4" y2="4" stroke={c} strokeWidth="1.2" />
          <line x1="4" y1="-4" x2="-4" y2="4" stroke={c} strokeWidth="1.2" />
        </g>
      )
    case 'pendant':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <circle r="6" fill="white" stroke={c} strokeWidth="1.5" />
          <circle r="3" fill={c} />
        </g>
      )
    case 'sconce':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <path d="M 0 -6 A 6 6 0 0 1 0 6" fill="white" stroke={c} strokeWidth="1.5" />
          <line x1="0" y1="-6" x2="0" y2="6" stroke={c} strokeWidth="1.5" />
        </g>
      )
    case 'exhaust_fan':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <rect x="-6" y="-6" width="12" height="12" fill="white" stroke={c} strokeWidth="1.5" rx="1.5" />
          <line x1="-3.5" y1="0" x2="3.5" y2="0" stroke={c} strokeWidth="1.2" />
          <line x1="0" y1="-3.5" x2="0" y2="3.5" stroke={c} strokeWidth="1.2" />
        </g>
      )
    case 'coach_light':
      return (
        <g transform={`translate(${x}, ${y})`}>
          <polygon points="0,-7 7,0 0,7 -7,0" fill="white" stroke={c} strokeWidth="1.5" />
          <circle r="1.5" fill={c} />
        </g>
      )
    default:
      return (
        <g transform={`translate(${x}, ${y})`}>
          <circle r="6" fill="white" stroke={c} strokeWidth="1.5" />
        </g>
      )
  }
}

/**
 * Legend strip matching the existing FloorPlanCanvas legend items and colors.
 */
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
      {items.map(item => {
        const color = TYPE_COLORS[item.type] || '#444444'
        return (
          <div key={item.type} className="flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" className="block">
              {item.type === 'recessed' && (
                <>
                  <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
                  <circle cx="6" cy="6" r="1" fill={color} />
                </>
              )}
              {item.type === 'ceiling_fan' && (
                <>
                  <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
                  <line x1="2.5" y1="2.5" x2="9.5" y2="9.5" stroke={color} strokeWidth="1.2" />
                  <line x1="9.5" y1="2.5" x2="2.5" y2="9.5" stroke={color} strokeWidth="1.2" />
                </>
              )}
              {item.type === 'pendant' && (
                <>
                  <circle cx="6" cy="6" r="5" fill="white" stroke={color} strokeWidth="1.5" />
                  <circle cx="6" cy="6" r="2" fill={color} />
                </>
              )}
              {item.type === 'sconce' && (
                <>
                  <path d="M 6 1 A 5 5 0 0 1 6 11" fill="white" stroke={color} strokeWidth="1.5" />
                  <line x1="6" y1="1" x2="6" y2="11" stroke={color} strokeWidth="1.5" />
                </>
              )}
              {item.type === 'exhaust_fan' && (
                <>
                  <rect x="1" y="1" width="10" height="10" fill="white" stroke={color} strokeWidth="1.5" rx="1.5" />
                  <line x1="3" y1="6" x2="9" y2="6" stroke={color} strokeWidth="1.2" />
                  <line x1="6" y1="3" x2="6" y2="9" stroke={color} strokeWidth="1.2" />
                </>
              )}
              {item.type === 'coach_light' && (
                <>
                  <polygon points="6,1 11,6 6,11 1,6" fill="white" stroke={color} strokeWidth="1.5" />
                  <circle cx="6" cy="6" r="1.2" fill={color} />
                </>
              )}
            </svg>
            <span className="text-gray-600">{item.label}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function SchematicOverlay({ rooms, schematicLayout, imageUrl }) {
  const [thumbExpanded, setThumbExpanded] = useState(false)

  const totalFixtures = useMemo(() => {
    if (!rooms) return 0
    return rooms.reduce((sum, r) => sum + (r.fixtures?.length || 0), 0)
  }, [rooms])

  // Fallback: no schematic data available yet
  if (!schematicLayout) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="bg-charcoal-light px-4 py-2 flex items-center justify-between">
          <h3 className="text-white text-sm font-medium">Lighting Layout</h3>
        </div>
        <div className="p-2">
          {imageUrl ? (
            <div className="relative">
              <img
                src={imageUrl}
                alt="Uploaded floor plan"
                className="block w-full h-auto rounded border border-gray-200"
                draggable={false}
              />
              <div className="absolute inset-0 flex items-center justify-center bg-white/60 rounded">
                <p className="text-sm text-gray-500 bg-white px-4 py-2 rounded shadow-sm border border-gray-200">
                  Schematic layout is not available for this plan
                </p>
              </div>
            </div>
          ) : (
            <div className="aspect-[4/3] bg-gray-100 rounded flex items-center justify-center">
              <div className="text-center text-gray-400">
                <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <p className="text-sm">Upload a floor plan to see lighting layout</p>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  const { canvas, rooms: layoutRooms } = schematicLayout
  const canvasW = canvas?.width || 1000
  const canvasH = canvas?.height || 750

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-charcoal-light px-4 py-2 flex items-center justify-between">
        <h3 className="text-white text-sm font-medium">Lighting Layout</h3>
        {totalFixtures > 0 && (
          <span className="text-gray-400 text-xs">{totalFixtures} fixtures total</span>
        )}
      </div>

      {/* SVG Schematic */}
      <div className="p-2">
        <svg
          viewBox={`0 0 ${canvasW} ${canvasH}`}
          className="block w-full h-auto"
          style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
        >
          {/* Background */}
          <rect width={canvasW} height={canvasH} fill="#ffffff" rx="4" />

          {layoutRooms?.map((room, ri) => {
            const r = room.rect
            if (!r) return null

            return (
              <g key={`room-${ri}`}>
                {/* Room rectangle */}
                <rect
                  x={r.x}
                  y={r.y}
                  width={r.w}
                  height={r.h}
                  rx={8}
                  fill="#fafafa"
                  stroke="#d1d5db"
                  strokeWidth="1.5"
                />

                {/* Room label at top-left */}
                <text
                  x={r.x + 12}
                  y={r.y + 20}
                  fontSize="13"
                  fontWeight="600"
                  fill="#374151"
                >
                  {room.label || room.name}
                </text>

                {/* Fixture count badge at top-right */}
                {room.fixture_count != null && (
                  <text
                    x={r.x + r.w - 12}
                    y={r.y + 20}
                    fontSize="11"
                    fill="#9ca3af"
                    textAnchor="end"
                  >
                    {room.fixture_count} {room.fixture_count === 1 ? 'fixture' : 'fixtures'}
                  </text>
                )}

                {/* Fixture icons */}
                {room.fixtures?.map((f, fi) => (
                  <SvgFixtureIcon
                    key={`fixture-${ri}-${fi}`}
                    type={f.type}
                    x={f.x}
                    y={f.y}
                    color={f.color}
                  />
                ))}
              </g>
            )
          })}
        </svg>
      </div>

      {/* Reference plan thumbnail */}
      {imageUrl && (
        <div className="px-4 pb-3">
          <button
            type="button"
            onClick={() => setThumbExpanded(prev => !prev)}
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-700 transition-colors mb-2"
          >
            <svg
              className={`w-3 h-3 transition-transform ${thumbExpanded ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Reference Plan
          </button>
          {thumbExpanded && (
            <img
              src={imageUrl}
              alt="Original floor plan"
              className="rounded border border-gray-200 w-auto"
              style={{ maxHeight: 200 }}
              draggable={false}
            />
          )}
        </div>
      )}

      {/* Legend */}
      <Legend />
    </div>
  )
}
