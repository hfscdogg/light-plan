#!/usr/bin/env node
/**
 * Regression tests for the plan viewer (frontend/public/preview.html).
 *
 * Serves the real page against a stub LightPlan API in headless Chromium and
 * asserts the behaviour the sales team lost fixtures to:
 *
 *   - AI fixtures actually render on an uploaded plan
 *   - fixtures placed by hand survive the analysis landing a minute later
 *   - every page of a multi-page plan set is analyzed up front, and printed
 *   - ceiling heights are asked per floor and sent with each page
 *   - spaces the plan left unnamed are offered for naming
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

// A space with no name printed in it: the AI guessed "Closet".
const UNNAMED_BATH = {
  id: 'r3', name: 'Closet', room_type: 'closet', labeled: false,
  position_x: 0.15, position_y: 0.8,
  bbox_x1: 0.1, bbox_y1: 0.75, bbox_x2: 0.2, bbox_y2: 0.85,
  fixtures: [
    { id: 'f5', fixture_type: 'recessed', plan_x: 0.15, plan_y: 0.8, position_x: 0.5, position_y: 0.5, is_prewire: false, product_desc: 'DMF DID Series' },
  ],
}
// What the server lays out once the user says that space is a bath.
const BATH_FIXTURES = [
  { id: 'f6', fixture_type: 'sconce', plan_x: 0.12, plan_y: 0.77, position_x: 0.3, position_y: 0.1, is_prewire: false, product_desc: 'WAC sconce' },
  { id: 'f7', fixture_type: 'exhaust_fan', plan_x: 0.15, plan_y: 0.8, position_x: 0.5, position_y: 0.5, is_prewire: false, product_desc: 'Panasonic fan' },
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
      const params = new URL(req.url, 'http://x').searchParams
      const pageNo = Number(params.get('page') || 1)
      opts.pagesRequested.push(pageNo)
      opts.ceilings[pageNo] = params.get('ceiling_height')
      req.resume()
      req.on('end', () => setTimeout(() => send({
        floor_plan_id: 'stub-plan',
        status: 'assigned',
        rooms: opts.rooms || AI_ROOMS,
        page_count: opts.pageCount,
        pages_analyzed: opts.pagesAnalyzed,
        page: pageNo,
        ...(opts.measured !== undefined ? { measured_sqft: opts.measured, ceiling_height_ft: Number(params.get('ceiling_height')) } : {}),
      }, 201), opts.delayMs))
      return
    }
    if (req.method === 'PATCH' && req.url.includes('/rooms/')) {
      let body = ''
      req.on('data', c => { body += c })
      req.on('end', () => {
        const update = JSON.parse(body)
        opts.patches.push({ url: req.url, ...update })
        const id = req.url.split('/rooms/')[1]
        send({ ...UNNAMED_BATH, id, name: update.name, room_type: update.room_type, fixtures: BATH_FIXTURES })
      })
      return
    }
    if (req.method === 'OPTIONS') {
      res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'PATCH, POST', 'Access-Control-Allow-Headers': 'Content-Type' })
      return res.end()
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
  const serverOpts = { delayMs: 0, pageCount: 1, pagesAnalyzed: 1, pagesRequested: [], ceilings: {}, patches: [], ...opts }
  const server = await startServer(html, serverOpts)
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(e.message))
  if (opts.fakePdfPages) await page.addInitScript(fakePdfJs, opts.fakePdfPages)
  try {
    await page.goto(`http://localhost:${PORT}/preview.html`)
    await fn(page, pageErrors, serverOpts)
  } finally {
    await page.close()
    await new Promise(r => server.close(r))
  }
}

/**
 * Stand-in for pdf.js, installed before the page loads so the viewer's
 * loadPdfJs() finds it and never reaches the CDN. Each page renders a
 * different colour, so the drawing on screen says which page it is.
 */
function fakePdfJs(numPages) {
  const colours = ['#f4c7c3', '#c3f4cd', '#c3d3f4', '#f4ecc3', '#e3c3f4']
  window.pdfjsLib = {
    GlobalWorkerOptions: {},
    getDocument: () => ({
      promise: Promise.resolve({
        numPages,
        getPage: n => Promise.resolve({
          getViewport: ({ scale }) => ({ width: 400 * scale, height: 300 * scale }),
          render: ({ canvasContext, viewport }) => {
            canvasContext.fillStyle = colours[(n - 1) % colours.length]
            canvasContext.fillRect(0, 0, viewport.width, viewport.height)
            return { promise: Promise.resolve() }
          },
        }),
      }),
    }),
  }
}

const uploadPdf = page =>
  page.setInputFiles('#planFile', { name: 'olsten.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 stub') })

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

  // --- a single image has no page switcher --------------------------------
  await withPage(browser, html, {}, async page => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const tabs = await page.evaluate(() => ({
      shown: document.getElementById('pageTabs').classList.contains('show'),
      buttons: document.querySelectorAll('#pageTabs .pg-btn').length,
    }))
    check('a one-page plan shows no page switcher', !tabs.shown && tabs.buttons === 0,
      `switcher shown=${tabs.shown} with ${tabs.buttons} buttons`)
  })

  // --- every floor of a multi-page plan set can be reached -----------------
  // David's Olsten plan: one floor per PDF page. The viewer only ever showed
  // page 1, with no way to get to the other floors.
  await withPage(browser, html, { fakePdfPages: 3, pageCount: 3 }, async (page, pageErrors, server) => {
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const first = await page.evaluate(() => ({
      buttons: [...document.querySelectorAll('#pageTabs .pg-btn')].map(b => b.dataset.page),
      src: document.getElementById('planImg').src,
      title: document.getElementById('sheetTitle').textContent,
      note: document.getElementById('aiNote').textContent,
    }))
    check('a 3-page PDF offers all 3 pages', first.buttons.join(',') === '1,2,3',
      `page buttons: [${first.buttons.join(',')}]`)
    check('the sheet title says which page is shown', first.title.includes('Page 1 of 3'),
      `title was "${first.title}"`)
    check('the note points at the other pages', first.note.includes('3 pages'),
      `note was: ${first.note.trim().slice(0, 200)}`)

    // Marshall: the second floor stayed empty until he clicked back and
    // forth. Every page is read without being opened.
    await page.waitForFunction(() => sheets.every(s => s.status === 'done' && s.src), null, { timeout: 20000 })
    const upFront = await page.evaluate(() => sheets.map(s => s.placed.length).join(','))
    check('every page is analyzed without being opened',
      server.pagesRequested.slice().sort().join(',') === '1,2,3' && upFront === '4,4,4',
      `analysis requested for pages [${server.pagesRequested}], fixtures per page [${upFront}]`)

    await page.click('#pageTabs .pg-btn[data-page="2"]')
    await page.waitForFunction(() => /Page 2 of 3/.test(document.getElementById('sheetTitle').textContent))
    await page.waitForFunction(() => placed.length === 4)

    const second = await page.evaluate(() => ({
      src: document.getElementById('planImg').src,
      onScreen: document.querySelectorAll('.marker[data-source="custom"]').length,
      visible: document.querySelectorAll('.marker[data-source="custom"].on').length,
      page1: sheets[0].placed.length,
    }))
    check('switching pages shows that page\'s drawing', second.src !== first.src && second.src.startsWith('data:image/png'),
      'the plan image did not change')
    check('opening an analyzed page does not read it again', server.pagesRequested.length === 3,
      `analysis requested for pages [${server.pagesRequested}]`)
    check('only the shown page\'s fixtures are on the drawing', second.onScreen === 4 && second.visible === 4,
      `${second.onScreen} markers on screen, ${second.visible} visible — page 1's fixtures leaked onto page 2?`)
    check('page 1 keeps its fixtures while page 2 is shown', second.page1 === 4,
      `page 1 has ${second.page1} fixtures`)

    await page.click('#pageTabs .pg-btn[data-page="1"]')
    await page.waitForFunction(() => /Page 1 of 3/.test(document.getElementById('sheetTitle').textContent))
    const back = await page.evaluate(() => ({
      src: document.getElementById('planImg').src,
      onScreen: document.querySelectorAll('.marker[data-source="custom"].on').length,
      ambient: document.querySelector('[data-count="ambient"]').textContent,
    }))
    check('going back to page 1 restores its drawing and fixtures', back.src === first.src && back.onScreen === 4,
      `${back.onScreen} fixtures on screen`)
    check('revisiting a page does not re-run its analysis', server.pagesRequested.length === 3,
      `analysis requested for pages [${server.pagesRequested}]`)
    check('layer counts cover every page, not just the one shown', back.ambient === '9 pts',
      `ambient count read "${back.ambient}" — expected 3 per page across three pages`)

    const report = await page.evaluate(() => {
      const realPrint = window.print
      window.print = () => {}
      document.getElementById('pdfBtn').click()
      window.print = realPrint
      const r = document.getElementById('report')
      return {
        plans: r.querySelectorAll('.r-plan img').length,
        headings: [...r.querySelectorAll('.r-sheet')].map(h => h.textContent),
        fixtures: r.querySelectorAll('.r-plan .marker.on').length,
        schedule: r.querySelector('table').textContent,
      }
    })
    check('the PDF report includes every lit page, opened or not', report.plans === 3,
      `expected 3 floor plans in the report, found ${report.plans}`)
    check('each page in the report is labelled', report.headings.join(',') === 'Page 1,Page 2,Page 3',
      `headings: [${report.headings.join(',')}]`)
    check('the report draws each page\'s fixtures', report.fixtures === 12,
      `expected 12 fixtures across three pages, found ${report.fixtures}`)
    check('no page errors while switching pages', pageErrors.length === 0, pageErrors.join('; '))
  })

  // --- an analysis that lands after the user switched pages -----------------
  // It belongs to the page it was read from, not the page now on screen.
  await withPage(browser, html, { fakePdfPages: 2, pageCount: 2, delayMs: 1200 }, async (page, _errors, server) => {
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await page.click('#pageTabs .pg-btn[data-page="2"]')
    await page.waitForFunction(() => /Page 2 of 2/.test(document.getElementById('sheetTitle').textContent))
    await page.waitForFunction(() => sheets[0].placed.length === 4 && placed.length === 4, null, { timeout: 20000 })
    await page.waitForTimeout(200)

    const state = await page.evaluate(() => ({
      onScreen: document.querySelectorAll('.marker[data-source="custom"]').length,
      page1: sheets[0].placed.length,
      page2: sheets[1].placed.length,
      page1Detached: sheets[0].placed.every(f => !f._el.isConnected),
    }))
    check('a late result lands on its own page', state.page1 === 4 && state.page2 === 4,
      `page 1 has ${state.page1}, page 2 has ${state.page2}`)
    check('a late result is not drawn on the page on screen', state.onScreen === 4 && state.page1Detached,
      `${state.onScreen} markers on screen; page 1 fixtures detached: ${state.page1Detached}`)
    check('both pages were analyzed once each', server.pagesRequested.slice().sort().join(',') === '1,2',
      `analysis requested for pages [${server.pagesRequested}]`)
  })

  // --- a multi-page working file reopens with every page -------------------
  await withPage(browser, html, { fakePdfPages: 3, pageCount: 3 }, async page => {
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await page.waitForFunction(() => sheets.every(s => s.status === 'done' && s.src), null, { timeout: 20000 })
    await page.click('#pageTabs .pg-btn[data-page="3"]')
    await page.waitForFunction(() => /Page 3 of 3/.test(document.getElementById('sheetTitle').textContent))
    await page.waitForFunction(() => placed.length === 4)

    const restored = await page.evaluate(async () => {
      window.prompt = () => 'Olsten'
      let href = null
      const realClick = HTMLAnchorElement.prototype.click
      HTMLAnchorElement.prototype.click = function () { href = this.href }
      document.getElementById('saveWorkBtn').click()
      HTMLAnchorElement.prototype.click = realClick
      const saved = JSON.parse(await (await fetch(href)).text())

      document.getElementById('demoBtn').click()
      restorePlan(saved)
      return {
        savedPages: saved.sheets.map(s => s.page),
        pages: sheets.map(s => s.page),
        shown: sheets[curSheet].page,
        counts: sheets.map(s => s.placed.length).join(','),
        onScreen: document.querySelectorAll('.marker[data-source="custom"]').length,
        buttons: document.querySelectorAll('#pageTabs .pg-btn').length,
      }
    })
    check('the working file keeps every page', restored.savedPages.join(',') === '1,2,3',
      `saved pages [${restored.savedPages}]`)
    check('reopening restores each page with its fixtures',
      restored.pages.join(',') === '1,2,3' && restored.counts === '4,4,4',
      `pages [${restored.pages}] with fixture counts [${restored.counts}]`)
    check('reopening returns to the page that was showing', restored.shown === 3 && restored.onScreen === 4,
      `showing page ${restored.shown} with ${restored.onScreen} markers`)
    check('reopening brings the page switcher back', restored.buttons === 3,
      `${restored.buttons} page buttons`)
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

  // --- a new plan uploaded while the last one is still being read ----------
  // The old plan's reads must not hold the new plan's pages in the queue.
  await withPage(browser, html, { fakePdfPages: 2, pageCount: 2, delayMs: 1500 }, async (page, pageErrors, server) => {
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await page.waitForFunction(() => sheets.every(s => s.status === 'reading'))
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await page.waitForFunction(() => sheets.every(s => s.status === 'done'), null, { timeout: 20000 }).catch(() => {})

    const state = await page.evaluate(() => ({
      statuses: sheets.map(s => s.status).join(','),
      counts: sheets.map(s => s.placed.length).join(','),
    }))
    check('a replacement plan is read even while the old one is still being read',
      state.statuses === 'done,done' && state.counts === '4,4',
      `statuses [${state.statuses}], fixtures [${state.counts}], requests [${server.pagesRequested}]`)
    check('no page errors when replacing a plan mid-read', pageErrors.length === 0, pageErrors.join('; '))
  })

  // --- ceiling height per floor, not square footage ------------------------
  // Marshall: "It should not ask me for the square footage ... It also really
  // needs to know ceiling heights (per-floor)."
  await withPage(browser, html, { fakePdfPages: 2, pageCount: 2, measured: 1480 }, async (page, pageErrors, server) => {
    await uploadPdf(page)
    await page.waitForSelector('#draftModal.show')
    const modal = await page.evaluate(() => ({
      sqft: !!document.getElementById('mSqft'),
      ceilings: [...document.querySelectorAll('#mCeilings label')].map(l => l.textContent),
    }))
    check('the draft form no longer asks for square footage', !modal.sqft, 'the sq ft field is still there')
    check('the draft form asks for a ceiling height per page',
      modal.ceilings.join('|') === 'Page 1 ceiling (ft)|Page 2 ceiling (ft)', `fields: [${modal.ceilings.join(' | ')}]`)
    check('nothing is analyzed before the ceilings are known', server.pagesRequested.length === 0,
      `analysis requested for pages [${server.pagesRequested}]`)

    await page.fill('#mCeil0', '10')
    await page.fill('#mCeil1', '8')
    await page.click('#mSkip')
    await page.waitForFunction(() => sheets.every(s => s.status === 'done'), null, { timeout: 20000 })

    check('each page is analyzed with its own ceiling height',
      server.ceilings[1] === '10' && server.ceilings[2] === '8', `sent ${JSON.stringify(server.ceilings)}`)

    const shown = await page.evaluate(() => ({
      note: document.getElementById('aiNote').textContent,
      summary: document.getElementById('exBody').textContent,
    }))
    check('the measured square footage is reported for the floor', /1,480 sq ft/.test(shown.note),
      `note: ${shown.note.trim().slice(0, 240)}`)
    check('the summary totals the measured floors', /2,960 sq ft/.test(shown.summary),
      `summary: ${shown.summary.trim().slice(0, 240)}`)
    check('no page errors with ceilings and measurements', pageErrors.length === 0, pageErrors.join('; '))
  })

  // --- spaces with no name on the plan are offered for naming ---------------
  // Marshall: "It ignores rooms that are not labeled, such as the baths on the
  // 2nd floor, closets, etc. Can it prompt you to name spaces?"
  await withPage(browser, html, { rooms: [...AI_ROOMS, UNNAMED_BATH] }, async (page, pageErrors, server) => {
    await uploadPlan(page)
    await page.waitForSelector('#draftModal.show')
    await page.click('#mSkip')
    await waitForAnalysis(page)

    const panel = await page.evaluate(() => ({
      shown: document.getElementById('nameSpaces').classList.contains('show'),
      rows: [...document.querySelectorAll('#nameSpaces .ns-name')].map(i => i.value),
      note: document.getElementById('aiNote').textContent,
      lit: placed.filter(f => f.room === 'Closet').length,
    }))
    check('an unnamed space is offered for naming', panel.shown && panel.rows.join(',') === 'Closet',
      `panel shown=${panel.shown} rows=[${panel.rows}]`)
    check('the note says spaces need names', /1 space has no name/.test(panel.note), `note: ${panel.note.trim().slice(0, 200)}`)
    check('the unnamed space is lit meanwhile', panel.lit === 1, `${panel.lit} fixtures in the unnamed space`)

    await page.hover('#nameSpaces .ns-row')
    const hl = await page.evaluate(() => {
      const el = document.getElementById('spaceHl')
      return { shown: el.classList.contains('show'), left: el.style.left, width: el.style.width }
    })
    check('hovering a space outlines it on the plan', hl.shown && hl.left === '10%' && parseFloat(hl.width) === 10,
      `highlight ${JSON.stringify(hl)}`)

    // A name another room already has is refused before anything is sent.
    await page.fill('#nameSpaces .ns-name', 'Kitchen')
    await page.click('#nameSpaces .ns-save')
    const clash = await page.evaluate(() => document.querySelector('#nameSpaces .ns-err')?.textContent || '')
    check('a name that is taken is refused', /already called Kitchen/.test(clash) && server.patches.length === 0,
      `error "${clash}", ${server.patches.length} saves sent`)

    await page.fill('#nameSpaces .ns-name', 'Hall Bath')
    await page.selectOption('#nameSpaces .ns-type', 'bathroom')
    await page.click('#nameSpaces .ns-save')
    await page.waitForFunction(() => !document.getElementById('nameSpaces').classList.contains('show'))

    const after = await page.evaluate(() => ({
      bath: placed.filter(f => f.room === 'Hall Bath').map(f => f.g).sort().join(','),
      closet: placed.filter(f => f.room === 'Closet').length,
      others: placed.filter(f => f.room === 'Kitchen' || f.room === 'Primary Bedroom').length,
      onScreen: document.querySelectorAll('.marker[data-source="custom"].on').length,
    }))
    const sent = server.patches[0] || {}
    check('naming a space saves it to the server',
      sent.name === 'Hall Bath' && sent.room_type === 'bathroom' && /\/plans\/stub-plan\/rooms\/r3$/.test(sent.url),
      `sent ${JSON.stringify(sent)}`)
    check('a space that is really a bath is relit as a bath', after.bath === 'fan,vanity' && after.closet === 0,
      `bath fixtures [${after.bath}], ${after.closet} left under "Closet"`)
    check('the other rooms are untouched', after.others === 4, `${after.others} fixtures in the other rooms`)
    check('the relit fixtures are drawn', after.onScreen === 6, `${after.onScreen} markers shown`)
    check('no page errors while naming spaces', pageErrors.length === 0, pageErrors.join('; '))
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
