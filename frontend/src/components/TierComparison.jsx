const ROOM_IMAGES = {
  kitchen:          '/images/tiers/kitchen.png',
  dining:           '/images/tiers/dining.png',
  living:           '/images/tiers/living.png',
  family:           '/images/tiers/living.png',
  great_room:       '/images/tiers/living.png',
  master_bedroom:   '/images/tiers/bedroom.png',
  bedroom:          '/images/tiers/bedroom.png',
  master_bathroom:  '/images/tiers/bedroom.png',
  bathroom:         '/images/tiers/bedroom.png',
}

export function getTierImage(roomType) {
  return ROOM_IMAGES[roomType] || null
}

export function TierComparison({ roomType, className = '' }) {
  const src = getTierImage(roomType)
  if (!src) return null

  return (
    <div className={`overflow-hidden rounded-md border border-bone-200 ${className}`}>
      <img
        src={src}
        alt={`Good / Better / Best lighting comparison — ${roomType.replace(/_/g, ' ')}`}
        className="w-full h-auto block"
        loading="lazy"
      />
    </div>
  )
}

export function TierComparisonCompact({ roomType, className = '' }) {
  const src = getTierImage(roomType)
  if (!src) return null

  return (
    <img
      src={src}
      alt={`Lighting tiers — ${roomType.replace(/_/g, ' ')}`}
      className={`w-full h-auto rounded border border-bone-200 ${className}`}
      loading="lazy"
    />
  )
}

export function TierGallery({ roomTypes, className = '' }) {
  const uniqueImages = []
  const seen = new Set()

  for (const rt of roomTypes) {
    const src = getTierImage(rt)
    if (src && !seen.has(src)) {
      seen.add(src)
      uniqueImages.push({ roomType: rt, src })
    }
  }

  if (uniqueImages.length === 0) return null

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="text-[10.5px] uppercase tracking-[0.24em] text-copper-700 font-semibold">
        What Each Tier Looks Like
      </div>
      {uniqueImages.map(({ roomType, src }) => (
        <div key={roomType}>
          <div className="text-xs text-ink-400 mb-1.5 capitalize font-medium">
            {roomType.replace(/_/g, ' ')}
          </div>
          <div className="overflow-hidden rounded-md border border-bone-200">
            <img
              src={src}
              alt={`Good / Better / Best — ${roomType.replace(/_/g, ' ')}`}
              className="w-full h-auto block"
              loading="lazy"
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export default TierComparison
