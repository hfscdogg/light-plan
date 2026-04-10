/**
 * Client-side lighting rules for instant tier preview.
 *
 * This is a simplified mirror of the backend rules engine. It computes
 * approximate fixture counts per room so the UI can show instant feedback
 * when the user toggles between Good/Better/Best without a server round-trip.
 *
 * The backend remains authoritative for exact positions and product SKUs.
 */

const TIER_MULTIPLIERS = {
  good: 1.0,
  better: 1.15,
  best: 1.3,
}

/**
 * Estimate recessed can count for a room.
 */
function estimateRecessedCount(widthFt, lengthFt, ceilingHeightFt = 9) {
  const spacing = ceilingHeightFt / 2
  const inset = Math.max(spacing / 2, 2)
  const effectiveW = Math.max(0, widthFt - 2 * inset)
  const effectiveL = Math.max(0, lengthFt - 2 * inset)

  if (effectiveW <= 0 || effectiveL <= 0) return 1

  const cols = Math.max(1, Math.floor(effectiveW / spacing) + 1)
  const rows = Math.max(1, Math.floor(effectiveL / spacing) + 1)
  return cols * rows
}

/**
 * Estimate fixtures for a single room at a given tier.
 * Returns an array of { type, qty, isPrewire } objects.
 */
export function estimateRoomFixtures(room, tier = 'better') {
  const width = room.width_ft || 12
  const length = room.length_ft || 12
  const ceiling = room.ceiling_height_ft || 9
  const multiplier = TIER_MULTIPLIERS[tier] || 1.15
  const fixtures = []

  const roomType = (room.room_type || 'other').toLowerCase()

  switch (roomType) {
    case 'kitchen': {
      const perimeter = 2 * (width + length)
      const cans = Math.max(4, Math.round(perimeter / 3))
      fixtures.push({ type: 'Recessed', qty: cans, isPrewire: false })
      fixtures.push({ type: 'Pendant', qty: tier === 'best' ? 2 : 1, isPrewire: true })
      if (tier !== 'good') {
        fixtures.push({ type: 'Under Cabinet', qty: 1, isPrewire: true })
      }
      break
    }

    case 'master_bedroom': {
      const target = { good: 4, better: 5, best: 6 }[tier] || 5
      fixtures.push({ type: 'Recessed', qty: target, isPrewire: false })
      fixtures.push({ type: 'Ceiling Fan', qty: 1, isPrewire: true })
      fixtures.push({ type: 'Switched Outlet', qty: 2, isPrewire: false })
      break
    }

    case 'bedroom': {
      const target = { good: 4, better: 4, best: 5 }[tier] || 4
      fixtures.push({ type: 'Recessed', qty: target, isPrewire: false })
      if (tier !== 'good') {
        fixtures.push({ type: 'Ceiling Fan', qty: 1, isPrewire: true })
      }
      fixtures.push({ type: 'Switched Outlet', qty: 1, isPrewire: false })
      break
    }

    case 'master_bathroom':
    case 'bathroom': {
      fixtures.push({ type: 'Sconce', qty: 2, isPrewire: false })
      fixtures.push({ type: 'Recessed', qty: tier !== 'good' ? 2 : 1, isPrewire: false })
      fixtures.push({ type: 'Exhaust Fan', qty: 1, isPrewire: false })
      break
    }

    case 'half_bath':
    case 'powder_room': {
      fixtures.push({ type: 'Recessed', qty: 1, isPrewire: false })
      if (tier !== 'good') {
        fixtures.push({ type: 'Sconce', qty: 1, isPrewire: false })
      }
      fixtures.push({ type: 'Exhaust Fan', qty: 1, isPrewire: false })
      break
    }

    case 'hallway':
    case 'entry':
    case 'foyer': {
      const spacingFt = { good: 6, better: 7, best: 8 }[tier] || 7
      const longDim = Math.max(width, length)
      const cans = Math.max(1, Math.round(longDim / spacingFt))
      fixtures.push({ type: 'Recessed', qty: cans, isPrewire: false })
      break
    }

    case 'living':
    case 'family':
    case 'great_room':
    case 'dining': {
      const base = estimateRecessedCount(width, length, ceiling)
      const target = Math.max(4, Math.round(base * multiplier))
      fixtures.push({ type: 'Recessed', qty: target, isPrewire: false })
      if (tier !== 'good') {
        fixtures.push({ type: 'Ceiling Fan', qty: 1, isPrewire: true })
      }
      if (tier === 'best') {
        fixtures.push({ type: 'Accent', qty: 3, isPrewire: true })
      }
      break
    }

    case 'garage':
    case 'porch':
    case 'patio':
    case 'exterior': {
      fixtures.push({ type: 'Coach Light', qty: roomType === 'garage' ? 2 : 1, isPrewire: false })
      if (tier !== 'good') {
        fixtures.push({ type: 'Landscape', qty: tier === 'best' ? 4 : 2, isPrewire: true })
      }
      break
    }

    default: {
      const base = estimateRecessedCount(width, length, ceiling)
      const target = Math.max(2, Math.round(base * multiplier))
      fixtures.push({ type: 'Recessed', qty: target, isPrewire: false })
      break
    }
  }

  return fixtures
}

/**
 * Estimate total fixture count across all rooms for a given tier.
 */
export function estimateTotalFixtures(rooms, tier = 'better') {
  let total = 0
  for (const room of rooms) {
    const fixtures = estimateRoomFixtures(room, tier)
    for (const f of fixtures) {
      total += f.qty
    }
  }
  return total
}
