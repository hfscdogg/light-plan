// Fills lightplan-one-pager.html from a prospect file and renders a one-page
// Letter PDF plus a PNG preview into out/.
// Usage: node marketing/one-pager/build.js [prospects/<builder>.json]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const dir = __dirname;
const configPath = path.resolve(dir, process.argv[2] || 'prospects/sample.json');
const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const slug = path.basename(configPath, '.json');

// Image paths are relative to the prospect file; the page lives in dir.
const rel = p => path.relative(dir, path.resolve(path.dirname(configPath), p));
const images = { bare: rel(cfg.planImage), lit: rel(cfg.litImage) };
const fields = {
  builder: cfg.builder,
  plan: cfg.plan,
  fixtures: String(cfg.fixtures),
  rooms: String(cfg.rooms.length),
  l1: cfg.levels[0], l2: cfg.levels[1], l3: cfg.levels[2], l4: cfg.levels[3],
  repName: cfg.rep.name, repTitle: cfg.rep.title, repPhone: cfg.rep.phone, repEmail: cfg.rep.email,
};

(async () => {
  const out = path.join(dir, 'out');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 2 });
  await page.goto('file://' + path.join(dir, 'lightplan-one-pager.html'), { waitUntil: 'networkidle' });
  await page.evaluate(({ fields, images }) => {
    document.querySelectorAll('[data-f]').forEach(el => {
      if (images[el.dataset.f]) el.src = images[el.dataset.f];
      else if (fields[el.dataset.f] != null) el.textContent = fields[el.dataset.f];
    });
  }, { fields, images });
  await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth));
  await page.evaluate(rooms => paintRooms(rooms), cfg.rooms);
  await page.evaluate(() => document.fonts.ready);

  const overflow = await page.evaluate(() => document.querySelector('.contrast').getBoundingClientRect().bottom >
    document.querySelector('.foot').getBoundingClientRect().top);
  if (overflow) console.warn('Warning: content runs into the footer; shorten the plan name.');

  const base = path.join(out, 'LightPlan-' + slug);
  await page.pdf({ path: base + '.pdf', width: '8.5in', height: '11in', printBackground: true, pageRanges: '1' });
  await page.screenshot({ path: base + '.png' });
  await browser.close();
  console.log('Wrote ' + path.relative(process.cwd(), base) + '.pdf');
})();
