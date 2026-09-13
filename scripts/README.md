# scripts/

Automation scripts for testing and operating LightPlan.

## preview-regression.mjs

Regression tests for the plan viewer (`frontend/public/preview.html`). Serves
the real page against a stub LightPlan API in headless Chromium and asserts the
behaviour the sales team lost fixtures to: AI fixtures render on an uploaded
plan, fixtures placed by hand survive the analysis landing a minute later,
skipped pages of a multi-page plan set are reported, and the demo sheet still
runs its tier intro.

No API key and no network — everything is stubbed locally, so this is safe to
run on every change.

```
cd scripts
npm install
npm run test:preview
```

Exits non-zero if any check fails. Set `CHROMIUM_PATH` to point at a Chromium
that Playwright did not install itself.
