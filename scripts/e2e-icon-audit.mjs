#!/usr/bin/env node
/**
 * Frontend-only icon-rendering audit.
 *
 * Boots Playwright against a LOCAL vite dev server, intercepts every
 * /api/* request, and serves canned rooms whose bounding boxes are
 * hand-traced against ~/Downloads/floorplantest.jpg. The canned data
 * includes a realistic spread of fixtures per room, with plan_x /
 * plan_y positions that exercise every corner of the image so we can
 * see whether FloorPlanCanvas is rendering cleanly.
 *
 * Writes three artifacts to scripts/screenshots/:
 *   - icon-audit-<stamp>.full.png         full page
 *   - icon-audit-<stamp>.layout.png       just the lighting layout panel
 *   - icon-audit-<stamp>.dom.json         per-icon DOM / computed position
 *                                         dump for programmatic inspection
 */

import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const APP_URL = process.env.APP_URL || 'http://127.0.0.1:5180'
const TEST_FILE = process.env.TEST_FILE || path.join(process.env.HOME, 'Downloads', 'floorplantest.jpg')

if (!fs.existsSync(TEST_FILE)) {
  console.error(`Test file not found: ${TEST_FILE}`)
  process.exit(1)
}

const outDir = path.join(__dirname, 'screenshots')
fs.mkdirSync(outDir, { recursive: true })
const stamp = new Date().toISOString().replace(/[:.]/g, '-')
const fullPath = path.join(outDir, `icon-audit-${stamp}.full.png`)
const layoutPath = path.join(outDir, `icon-audit-${stamp}.layout.png`)
const domPath = path.join(outDir, `icon-audit-${stamp}.dom.json`)

// ---------------------------------------------------------------------
// Canned room data hand-traced against floorplantest.jpg (600x812).
// bbox coordinates are fractions of the full image. Each room has a
// plausible set of fixtures at plausible plan_x / plan_y positions
// inside its bbox so the FloorPlanCanvas grid renders naturally.
// ---------------------------------------------------------------------

const ROOMS = [
  {
    id: 'r-garage',
    name: '3 Car Garage',
    room_type: 'garage',
    bbox: [0.09, 0.04, 0.38, 0.22],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed', 'recessed', 'recessed', 'coach_light', 'coach_light'],
  },
  {
    id: 'r-mud',
    name: 'Mud Room',
    room_type: 'mudroom',
    bbox: [0.24, 0.31, 0.37, 0.42],
    fixtures: ['recessed', 'recessed'],
  },
  {
    id: 'r-office',
    name: 'Office',
    room_type: 'office',
    bbox: [0.04, 0.30, 0.16, 0.37],
    fixtures: ['recessed', 'recessed', 'recessed'],
  },
  {
    id: 'r-screened',
    name: 'Screened Porch',
    room_type: 'porch',
    bbox: [0.32, 0.28, 0.66, 0.43],
    fixtures: ['recessed', 'recessed', 'ceiling_fan', 'coach_light'],
  },
  {
    id: 'r-master',
    name: 'Master Bedroom',
    room_type: 'master_bedroom',
    bbox: [0.60, 0.30, 0.90, 0.47],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed', 'recessed', 'ceiling_fan'],
  },
  {
    id: 'r-mbath',
    name: 'Master Bath',
    room_type: 'master_bathroom',
    bbox: [0.70, 0.46, 0.88, 0.58],
    fixtures: ['sconce', 'sconce', 'recessed', 'exhaust_fan'],
  },
  {
    id: 'r-closet',
    name: 'Closet / Safe Rm',
    room_type: 'walk_in_closet',
    bbox: [0.77, 0.55, 0.96, 0.66],
    fixtures: ['recessed', 'recessed'],
  },
  {
    id: 'r-breakfast',
    name: 'Breakfast',
    room_type: 'dining',
    bbox: [0.14, 0.44, 0.33, 0.55],
    fixtures: ['pendant', 'recessed', 'recessed'],
  },
  {
    id: 'r-kitchen',
    name: 'Kitchen',
    room_type: 'kitchen',
    bbox: [0.04, 0.55, 0.30, 0.68],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed', 'pendant', 'pendant'],
  },
  {
    id: 'r-family',
    name: 'Family Room',
    room_type: 'family',
    bbox: [0.32, 0.47, 0.66, 0.74],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed', 'recessed', 'recessed', 'ceiling_fan'],
  },
  {
    id: 'r-laundry',
    name: 'Laundry',
    room_type: 'laundry',
    bbox: [0.05, 0.76, 0.30, 0.88],
    fixtures: ['recessed', 'recessed'],
  },
  {
    id: 'r-foyer',
    name: 'Foyer',
    room_type: 'foyer',
    bbox: [0.34, 0.78, 0.56, 0.93],
    fixtures: ['pendant', 'recessed', 'recessed'],
  },
  {
    id: 'r-dining',
    name: 'Dining',
    room_type: 'dining',
    bbox: [0.10, 0.89, 0.32, 0.99],
    fixtures: ['pendant', 'recessed', 'recessed'],
  },
  {
    id: 'r-living',
    name: 'Living',
    room_type: 'living',
    bbox: [0.58, 0.89, 0.80, 0.99],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed'],
  },
  {
    id: 'r-nursery',
    name: 'Nursery / Guest',
    room_type: 'bedroom',
    bbox: [0.62, 0.70, 0.86, 0.86],
    fixtures: ['recessed', 'recessed', 'recessed', 'recessed', 'ceiling_fan'],
  },
]

// Spread N fixtures across a bbox in a grid with a 15% inset so the
// icons sit inside the room visually.
function positionFixturesInBbox(bbox, types) {
  const [x1, y1, x2, y2] = bbox
  const w = x2 - x1
  const h = y2 - y1
  const inset = 0.15
  const innerX = x1 + w * inset
  const innerY = y1 + h * inset
  const innerW = w * (1 - 2 * inset)
  const innerH = h * (1 - 2 * inset)

  const n = types.length
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * (innerW / Math.max(innerH, 1e-6)))))
  const rows = Math.max(1, Math.ceil(n / cols))

  const result = []
  for (let i = 0; i < n; i++) {
    const r = Math.floor(i / cols)
    const c = i % cols
    const fx = cols > 1 ? innerX + (innerW * c) / (cols - 1) : x1 + w / 2
    const fy = rows > 1 ? innerY + (innerH * r) / (rows - 1) : y1 + h / 2
    result.push({
      id: `f-${Math.random().toString(36).slice(2, 10)}`,
      fixture_type: types[i],
      plan_x: Math.round(fx * 1000) / 1000,
      plan_y: Math.round(fy * 1000) / 1000,
      position_x: 0.5,
      position_y: 0.5,
      product_sku: 'TEST',
      product_desc: 'Test fixture',
      msrp_range: '$50-100',
      zone: 'test',
      notes: '',
      is_prewire: types[i] === 'ceiling_fan',
    })
  }
  return result
}

function buildRoomResponse() {
  return ROOMS.map(r => ({
    id: r.id,
    name: r.name,
    room_type: r.room_type,
    sqft: 150,
    width_ft: 12,
    length_ft: 12,
    ceiling_height_ft: 9,
    position_x: (r.bbox[0] + r.bbox[2]) / 2,
    position_y: (r.bbox[1] + r.bbox[3]) / 2,
    bbox_x1: r.bbox[0],
    bbox_y1: r.bbox[1],
    bbox_x2: r.bbox[2],
    bbox_y2: r.bbox[3],
    fixtures: positionFixturesInBbox(r.bbox, r.fixtures),
  }))
}

const CANNED_PROJECT = {
  id: 'test-project',
  name: 'Icon Audit',
  address: '',
  status: 'assigned',
  tier: 'better',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  builder_id: null,
  floor_plans: [],
}

const CANNED_PLAN_RESPONSE = {
  floor_plan_id: 'test-plan',
  status: 'assigned',
  rooms: buildRoomResponse(),
}

// ---------------------------------------------------------------------

console.log(`→ target:     ${APP_URL}`)
console.log(`→ test file:  ${TEST_FILE}`)
console.log(`→ canned data: ${CANNED_PLAN_RESPONSE.rooms.length} rooms, ${
  CANNED_PLAN_RESPONSE.rooms.reduce((s, r) => s + r.fixtures.length, 0)
} fixtures`)

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1500, height: 2000 },
  deviceScaleFactor: 2,
})
const page = await context.newPage()

page.on('console', msg => {
  const t = msg.type()
  if (t === 'error' || t === 'warning') console.log(`[browser:${t}] ${msg.text()}`)
})
page.on('pageerror', err => console.error('[browser:pageerror]', err.message))

// Intercept /api/** and serve canned data
await page.route('**/api/**', async route => {
  const req = route.request()
  const url = new URL(req.url())
  const pathname = url.pathname
  const method = req.method()

  if (method === 'GET' && pathname === '/api/projects') {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  }
  if (method === 'POST' && pathname === '/api/projects') {
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(CANNED_PROJECT) })
  }
  if (method === 'POST' && /^\/api\/projects\/[^/]+\/plans\/upload$/.test(pathname)) {
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(CANNED_PLAN_RESPONSE) })
  }
  if (method === 'PATCH' && /^\/api\/projects\/[^/]+$/.test(pathname)) {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CANNED_PROJECT) })
  }
  // Default: 404
  return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not mocked"}' })
})

console.log('→ opening app')
await page.goto(APP_URL, { waitUntil: 'domcontentloaded' })

// Click "New Project"
const newBtn = page.getByRole('button', { name: /new project/i })
await newBtn.waitFor({ timeout: 10_000 })
await newBtn.click()

console.log('→ filling form + uploading test image')
await page.locator('#project-name').fill('Icon Audit')
await page.locator('input[type="file"]').setInputFiles(TEST_FILE)

console.log('→ waiting for results view')
await page.getByText('Lighting Layout', { exact: true }).waitFor({ timeout: 30_000 })

// Give the image a beat to load so layout measurements are stable
await page.waitForTimeout(1200)
await page.evaluate(() => {
  const img = document.querySelector('img[alt="Uploaded floor plan"]')
  if (!img) return
  return new Promise(resolve => {
    if (img.complete && img.naturalWidth) return resolve()
    img.addEventListener('load', () => resolve(), { once: true })
  })
})
await page.waitForTimeout(400)

console.log(`→ saving full-page screenshot → ${fullPath}`)
await page.screenshot({ path: fullPath, fullPage: true })

// Grab just the lighting layout card
const card = page.locator('div.bg-white.rounded-lg.border').filter({
  has: page.getByText('Lighting Layout', { exact: true }),
}).first()
await card.screenshot({ path: layoutPath })
console.log(`→ saved layout panel        → ${layoutPath}`)

// Dump DOM/computed info for every icon + label
const dom = await page.evaluate(() => {
  const img = document.querySelector('img[alt="Uploaded floor plan"]')
  const imgRect = img?.getBoundingClientRect()

  const icons = Array.from(document.querySelectorAll('.absolute.pointer-events-auto.cursor-pointer, .absolute .pointer-events-auto, [title]')).filter(el => el.querySelector('svg'))
  // More robust: grab every absolutely-positioned element inside the overlay div
  const overlay = document.querySelector('div.absolute.inset-0.pointer-events-none')
  const children = overlay ? Array.from(overlay.querySelectorAll(':scope > div')) : []

  const items = children.map(el => {
    const rect = el.getBoundingClientRect()
    const style = window.getComputedStyle(el)
    const hasSvg = !!el.querySelector('svg')
    const label = el.textContent?.trim() || ''
    return {
      left_px: rect.left,
      top_px: rect.top,
      width_px: rect.width,
      height_px: rect.height,
      left_css: el.style.left,
      top_css: el.style.top,
      transform: style.transform,
      zIndex: style.zIndex,
      hasSvg,
      label,
    }
  })

  return {
    image: imgRect && {
      left: imgRect.left,
      top: imgRect.top,
      width: imgRect.width,
      height: imgRect.height,
    },
    overlayCount: children.length,
    overlayChildren: items,
  }
})
fs.writeFileSync(domPath, JSON.stringify(dom, null, 2))
console.log(`→ saved DOM dump            → ${domPath}`)

await browser.close()
console.log('✓ done')
