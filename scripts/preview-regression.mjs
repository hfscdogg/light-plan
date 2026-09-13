#!/usr/bin/env node
/**
 * Regression tests for the plan viewer (frontend/public/preview.html).
 *
 * Serves the real page against a stub LightPlan API in headless Chromium and
 * asserts the behaviour the sales team lost fixtures to:
 *
 *   - AI fixtures actually render on an uploaded plan
 *   - fixtures placed by hand survive the analysis landing a minute later
 *   - skipped pages of a multi-page plan set are reported
 *   - the demo sheet still runs its tier intro
 *
 * No API key and no network: everything is stubbed locally.
 *
 *   node preview-regression.mjs
 *
 * Set CHROMIUM_PATH to use a Chromium that Playwright did not install itself.
 */

import { chromium } from 'playwright'
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PAGE = path.join(HERE, '..', 'frontend', 'public', 'preview.html')
const PORT = Number(process.env.PORT || 8971)

// 1x1 PNG. The stub server never looks at it; the page just needs a file.
const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

const AI_ROOMS = [
  {
    id: 'r1', name: 'Kitchen', room_type: 'kitchen',
    position_x: 0.3, position_y: 0.4,
    bbox_x1: 0.2, bbox_y1: 0.3, bbox_x2: 0.4, bbox_y2: 0.5,
    fixtures: [
      { id: 'f1', fixture_type: 'recessed', plan_x: 0.30, plan_y: 0.40, position_x: 0.5, position_y: 0.5, is_prewire: false, product_desc: 'DMF DID Series' },
      { id: 'f2', fixture_type: 'pendant', plan_x: 0.33, plan_y: 0.42, position_x: 0.5, position_y: 0.4, is_prewire: true, product_desc: 'WAC pendant' },
    ],
  },
  {
    id: 'r2', name: 'Primary Bedroom', room_type: 'master_bedroom',
    position_x: 0.7, position_y: 0.6,
    bbox_x1: 0.6, bbox_y1: 0.5, bbox_x2: 0.85, bbox_y2: 0.75,
    fixtures: [
      { id: 'f3', fixture_type: 'recessed', plan_x: 0.65, plan_y: 0.55, position_x: 0.2, position_y: 0.2, is_prewire: false, product_desc: 'DMF DID Series' },
      { id: 'f4', fixture_type: 'ceiling_fan', plan_x: 0.72, plan_y: 0.62, position_x: 0.5, position_y: 0.5, is_prewire: true, product_desc: 'Modern Forms fan' },
    ],
  },
]

/** Stub API. `opts` lets each test choose the analysis delay and page counts. */
function startServer(html, opts) {
  const server = http.createServer((req, res) => {
    const send = (body, code = 200) => {
      res.writeHead(code, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' })
      res.end(JSON.stringify(body))
    }
    if (req.url === '/preview.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      return res.end(html)
    }
    if (req.url === '/api/health') return send({ status: 'ok' })
    if (req.url === '/api/projects' && req.method === 'POST') {
      req.resume()
      return send({ id: 'stub-project' })
    }
    if (req.url.includes('/plans/upload')) {
      req.resume()
      req.on('end', () => setTimeout(() => send({
        floor_plan_id: 'stub-plan',
        status: 'assigned',
        rooms: AI_ROOMS,
        page_count: opts.pageCount,
        pages_analyzed: opts.pagesAnalyzed,
      }, 201), opts.delayMs))
      return
    }
    res.writeHead(404)
    res.end()
  })
  return new Promise(resolve => server.listen(PORT, () => resolve(server)))
}

const results = []
function check(name, condition, detail) {
  results.push({ name, ok: Boolean(condition), detail })
  const mark = condition ? '  ok  ' : ' FAIL '
  console.log(`${mark} ${name}${condition || !detail ? '' : `\n         ${detail}`}`)
}

async function withPage(browser, html, opts, fn) {
  const server = await startServer(html, { delayMs: 0, pageCount: 1, pagesAnalyzed: 1, ...opts })
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(e.message))
  try {
    await page.goto(`http://localhost:${PORT}/preview.html`)
    await fn(page, pageErrors)
  } finally {
    await page.close()
    await new Promise(r => server.close(r))
  }
}

const uploadPlan = page =>
  page.setInputFiles('#planFile', { name: 'plan.png', mimeType: 'image/png', buffer: TINY_PNG })

const waitForAnalysis = page =>
  page.waitForFunction(
    () => /AI read|could not finish|ask Livewire/.test(document.getElementById('aiNote').textContent),
    { timeout: 20000 },
  )

// Plain-JSON copy for page.evaluate, which serialises its argument.
const AI_ROOMS_FOR_PAGE = JSON.parse(JSON.stringify(AI_ROOMS))

async function main() {
  const html = fs.readFileSync(PAGE, 'utf8')
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    args: ['--no-sandbox'],
  })

  // --- AI fixtures render on an uploaded plan -----------------------------
  await withPage(browser, html, {}, async (page, pageErrors) => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const state = await page.evaluate(() => ({
      markers: document.querySelectorAll('.marker[data-source="custom"]').length,
      visible: document.querySelectorAll('.marker[data-source="custom"].on').length,
      note: document.getElementById('aiNote').textContent,
    }))

    check('AI fixtures are drawn on the plan', state.markers === 4,
      `expected 4 markers, got ${state.markers} — note: ${state.note.trim().slice(0, 120)}`)
    check('AI fixtures are visible, not just in the DOM', state.visible === 4,
      `expected 4 visible, got ${state.visible}`)
    check('no page errors during analysis', pageErrors.length === 0, pageErrors.join('; '))
  })

  // --- hand-placed fixtures survive the analysis landing -------------------
  await withPage(browser, html, { delayMs: 1500 }, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mGo')
    await page.waitForSelector('#roomChips .rc-btn')

    const box = await page.locator('#planWrap').boundingBox()
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.3)
    const byHand = await page.evaluate(() => placed.length)

    await waitForAnalysis(page)
    await page.waitForTimeout(250)

    const after = await page.evaluate(() => ({
      total: placed.length,
      kept: placed.filter(f => !f.ai).length,
      fromAi: placed.filter(f => f.ai).length,
      visible: document.querySelectorAll('.marker[data-source="custom"].on').length,
    }))

    check('hand-placed fixtures survive the AI result', after.kept === byHand,
      `placed ${byHand} by hand, ${after.kept} survived`)
    check('AI fixtures are added alongside them', after.fromAi === 4,
      `expected 4 AI fixtures, got ${after.fromAi}`)
    check('every surviving fixture stays visible', after.visible === after.total,
      `${after.visible} visible of ${after.total} placed`)
  })

  // --- fixtures can be dragged to fine-tune -------------------------------
  // The plan image is natively draggable; pressing a marker over it used to
  // start an HTML5 image drag, which fires pointercancel and strands the
  // fixture after a single move.
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const marker = page.locator('.marker[data-source="custom"]').first()
    const mb = await marker.boundingBox()
    const wb = await page.locator('#planWrap').boundingBox()
    const vp = page.viewportSize()

    const tx = Math.min(wb.x + wb.width * 0.75, vp.width - 20)
    const ty = Math.min(wb.y + wb.height * 0.75, vp.height - 20)
    const expectX = ((tx - wb.x) / wb.width) * 100
    const expectY = ((ty - wb.y) / wb.height) * 100

    const cancelled = await page.evaluate(() => {
      window.__nativeDrag = 0
      addEventListener('dragstart', () => { window.__nativeDrag++ }, true)
      addEventListener('pointercancel', () => { window.__nativeDrag++ }, true)
      return true
    })

    await page.mouse.move(mb.x + mb.width / 2, mb.y + mb.height / 2)
    await page.mouse.down()
    await page.mouse.move(tx, ty, { steps: 25 })
    await page.mouse.up()
    await page.waitForTimeout(200)

    const after = await page.evaluate(() => ({
      pos: placed[0], native: window.__nativeDrag,
    }))
    const dx = Math.abs(after.pos.x - expectX)
    const dy = Math.abs(after.pos.y - expectY)

    check('a fixture can be dragged', dx < 50 || dy < 50,
      `fixture did not move (still at ${after.pos.x}, ${after.pos.y})`)
    check('a dragged fixture follows the pointer', dx < 1.5 && dy < 1.5,
      `expected ~${expectX.toFixed(1)},${expectY.toFixed(1)} — got ${after.pos.x},${after.pos.y}`)
    check('dragging does not trigger a native image drag', after.native === 0,
      `${after.native} dragstart/pointercancel events fired`)
  })

  // --- a re-run replaces AI fixtures without duplicating them --------------
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const count = await page.evaluate(rooms => {
      applyServerRooms(rooms, { total: 1, analyzed: 1 })
      return placed.filter(f => f.ai).length
    }, AI_ROOMS_FOR_PAGE)
    check('re-running analysis does not duplicate fixtures', count === 4,
      `expected 4 AI fixtures after a second pass, got ${count}`)
  })

  // --- skipped pages of a plan set are reported ----------------------------
  await withPage(browser, html, { pageCount: 6, pagesAnalyzed: 1 }, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const note = await page.evaluate(() => document.getElementById('aiNote').textContent)
    check('multi-page plan set reports what was skipped',
      note.includes('6 pages') && note.includes('only page 1'),
      `note was: ${note.trim().slice(0, 200)}`)
  })

  // --- the PDF report contains the drawing, not just a table ---------------
  // @media print hides <main>, so the report used to print with no floor plan
  // and no fixtures at all — a text document where a lighting plan should be.
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const report = await page.evaluate(() => {
      const realPrint = window.print
      window.print = () => {}
      document.getElementById('pdfBtn').click()
      window.print = realPrint
      const r = document.getElementById('report')
      return {
        plans: r.querySelectorAll('.r-plan img').length,
        fixtures: r.querySelectorAll('.r-plan .marker.on').length,
        legend: r.querySelectorAll('.r-legend .r-key').length,
        editing: r.querySelectorAll('.hotspot, .plan-veil, .marker:not(.on)').length,
      }
    })

    check('the PDF report includes the floor plan', report.plans === 1,
      `expected 1 plan image in the report, found ${report.plans}`)
    check('the PDF report shows the fixtures on it', report.fixtures === 4,
      `expected 4 fixtures drawn on the report plan, found ${report.fixtures}`)
    check('the PDF report keys the icons to products', report.legend > 0,
      'no legend entries — printed icons would be unlabelled')
    check('the PDF report drops editing affordances', report.editing === 0,
      `${report.editing} screen-only elements leaked into the report`)
  })

  // --- Save plan produces the PDF, not a data file -------------------------
  // Reported twice from the field: "Save plan" handing back JSON is not what
  // anyone means by saving a plan.
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const result = await page.evaluate(async () => {
      window.__printed = 0
      const realPrint = window.print
      window.print = () => { window.__printed++ }
      window.prompt = () => 'Smith Residence'
      let downloaded = null
      const realClick = HTMLAnchorElement.prototype.click
      HTMLAnchorElement.prototype.click = function () { if (this.download) downloaded = this.download }

      document.getElementById('saveBtn').click()

      const out = {
        printed: window.__printed,
        downloaded,
        planInReport: document.querySelectorAll('#report .r-plan img').length,
      }
      window.print = realPrint
      HTMLAnchorElement.prototype.click = realClick
      return out
    })

    check('Save plan produces the PDF plan', result.printed === 1,
      `expected the print path to run once, ran ${result.printed} times`)
    check('Save plan does not hand back a data file', result.downloaded === null,
      `it downloaded "${result.downloaded}" instead`)
    check('the saved PDF contains the drawing', result.planInReport === 1,
      'the report built by Save plan has no floor plan in it')
  })

  // --- the working file is still available and still round-trips ------------
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const saved = await page.evaluate(() => {
      window.prompt = () => 'Smith Residence'
      let name = null, href = null
      const realClick = HTMLAnchorElement.prototype.click
      HTMLAnchorElement.prototype.click = function () { name = this.download; href = this.href }
      document.getElementById('saveWorkBtn').click()
      HTMLAnchorElement.prototype.click = realClick
      return { name, isBlob: String(href).startsWith('blob:') }
    })

    check('the working file is still downloadable', saved.name === 'Smith-Residence.lightplan.json',
      `expected Smith-Residence.lightplan.json, got "${saved.name}"`)
    check('the working file is real content', saved.isBlob,
      'the download had no blob behind it')
  })

  // --- the untouched demo sheet still runs its intro ------------------------
  await withPage(browser, html, {}, async page => {
    await page.waitForTimeout(2000)
    const demo = await page.evaluate(() => ({
      tier: document.getElementById('tierName').textContent,
      lit: document.querySelectorAll('.marker[data-source="preset"].on').length,
    }))
    check('demo sheet still animates to Level 1', demo.tier.includes('Level 1'),
      `tier showed "${demo.tier}"`)
    check('demo sheet still lights its fixtures', demo.lit > 0,
      `${demo.lit} demo fixtures lit`)
  })

  await browser.close()

  const failed = results.filter(r => !r.ok)
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  if (failed.length) {
    console.log(`\nFailed:\n${failed.map(f => `  - ${f.name}`).join('\n')}`)
    process.exitCode = 1
  }
}

main().catch(err => {
  console.error(err)
  process.exitCode = 1
})
