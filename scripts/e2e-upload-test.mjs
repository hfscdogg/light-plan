#!/usr/bin/env node
/**
 * End-to-end smoke test for the LightPlan upload flow.
 *
 * Opens the deployed (or local) app, uploads a floor plan file, waits for
 * the results view to render, and saves a full-page screenshot to
 * scripts/screenshots/. Use this to iterate on the layout / icon placement
 * without hand-uploading through the browser every time.
 *
 * Usage:
 *   node e2e-upload-test.mjs --file ./sample.pdf
 *   node e2e-upload-test.mjs --url https://lightplan-production.up.railway.app --file ./plan.png
 *   node e2e-upload-test.mjs --file ./plan.pdf --name "Dover V" --auth user:pass
 *
 * Exit codes:
 *   0 — upload succeeded, screenshot saved
 *   1 — bad arguments
 *   2 — upload or navigation failed; screenshot of failure state still saved
 */

import { chromium } from 'playwright'
import { parseArgs } from 'node:util'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const { values } = parseArgs({
  options: {
    url:     { type: 'string', default: 'https://lightplan-production.up.railway.app' },
    file:    { type: 'string' },
    name:    { type: 'string', default: 'Playwright Test' },
    address: { type: 'string', default: '' },
    out:     { type: 'string' },
    auth:    { type: 'string' },            // "user:pass" for HTTP basic auth
    headed:  { type: 'boolean', default: false },
    timeout: { type: 'string', default: '180' }, // seconds for the parse wait
  },
})

if (!values.file) {
  console.error('Usage: node e2e-upload-test.mjs --file <path-to-plan> [--url URL] [--name NAME]')
  process.exit(1)
}

const filePath = path.resolve(values.file)
if (!fs.existsSync(filePath)) {
  console.error(`File not found: ${filePath}`)
  process.exit(1)
}

const outDir = values.out || path.join(__dirname, 'screenshots')
fs.mkdirSync(outDir, { recursive: true })
const stamp = new Date().toISOString().replace(/[:.]/g, '-')
const fileStem = path.basename(filePath, path.extname(filePath))
const outPath = path.join(outDir, `${fileStem}-${stamp}.png`)
const failPath = path.join(outDir, `${fileStem}-${stamp}.fail.png`)

const contextOpts = {
  viewport: { width: 1400, height: 2000 },
  deviceScaleFactor: 2,
}
if (values.auth) {
  const [username, password] = values.auth.split(':')
  contextOpts.httpCredentials = { username, password }
}

const parseTimeoutMs = Number(values.timeout) * 1000

console.log(`→ target:   ${values.url}`)
console.log(`→ file:     ${filePath}`)
console.log(`→ project:  ${values.name}`)
console.log(`→ headless: ${!values.headed}`)

const browser = await chromium.launch({ headless: !values.headed })
const context = await browser.newContext(contextOpts)
const page = await context.newPage()

page.on('console', msg => {
  const type = msg.type()
  if (type === 'error' || type === 'warning') {
    console.log(`[browser:${type}] ${msg.text()}`)
  }
})
page.on('pageerror', err => console.error('[browser:pageerror]', err.message))
page.on('requestfailed', req =>
  console.warn(`[browser:requestfailed] ${req.method()} ${req.url()} — ${req.failure()?.errorText}`)
)

async function saveFailShot(label) {
  try {
    await page.screenshot({ path: failPath, fullPage: true })
    console.error(`✗ ${label} — screenshot saved to ${failPath}`)
  } catch (err) {
    console.error(`✗ ${label} — and screenshot also failed:`, err.message)
  }
}

try {
  console.log('→ opening app')
  await page.goto(values.url, { waitUntil: 'domcontentloaded', timeout: 60_000 })

  // If we land on the list view, click "New Project" to reach the upload form.
  const newProjectBtn = page.getByRole('button', { name: /new project/i })
  if (await newProjectBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('→ clicking "New Project"')
    await newProjectBtn.click()
  }

  console.log('→ filling project name')
  await page.locator('#project-name').fill(values.name)

  if (values.address) {
    await page.locator('#project-address').fill(values.address)
  }

  console.log('→ uploading file')
  await page.locator('input[type="file"]').setInputFiles(filePath)

  console.log(`→ waiting for results (up to ${values.timeout}s)`)
  // Race: either the results view header appears, or an error banner shows.
  const resultsHeader = page.getByText('Lighting Layout', { exact: true })
  const errorBanner = page
    .locator('div.bg-red-50, div.text-red-700')
    .filter({ hasText: /./ })

  const winner = await Promise.race([
    resultsHeader.waitFor({ timeout: parseTimeoutMs }).then(() => 'results'),
    errorBanner.first().waitFor({ timeout: parseTimeoutMs }).then(() => 'error'),
  ]).catch(() => null)

  if (winner === 'error') {
    const text = (await errorBanner.first().textContent())?.trim()
    console.error(`✗ upload rejected by server: ${text}`)
    await saveFailShot('upload error')
    await browser.close()
    process.exit(2)
  }
  if (winner !== 'results') {
    await saveFailShot('timed out waiting for results')
    await browser.close()
    process.exit(2)
  }

  // Let icons finish positioning + any late network settle.
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(1500)

  console.log(`→ saving screenshot → ${outPath}`)
  await page.screenshot({ path: outPath, fullPage: true })

  // Also capture just the lighting layout panel on its own for focused review.
  const panelPath = outPath.replace(/\.png$/, '.layout.png')
  const layoutPanel = page
    .locator('div')
    .filter({ has: page.getByText('Lighting Layout', { exact: true }) })
    .first()
  await layoutPanel.screenshot({ path: panelPath }).catch(err => {
    console.warn(`(could not snap layout panel only: ${err.message})`)
  })

  console.log('✓ done')
} catch (err) {
  console.error('✗ test failed:', err.message)
  await saveFailShot('unexpected error')
  await browser.close()
  process.exit(2)
}

await browser.close()
