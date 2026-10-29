// Renders lightplan-one-pager.html to a one-page Letter PDF and a PNG preview.
// Usage: node marketing/one-pager/build.js
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const dir = __dirname;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 2 });
  await page.goto('file://' + path.join(dir, 'lightplan-one-pager.html'), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: path.join(dir, 'LightPlan-One-Pager.pdf'), width: '8.5in', height: '11in', printBackground: true, pageRanges: '1' });
  await page.screenshot({ path: path.join(dir, 'LightPlan-One-Pager.png') });
  await browser.close();
})();
