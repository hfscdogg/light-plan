# scripts/

Automation scripts for testing and operating LightPlan.

## e2e-upload-test.mjs

End-to-end smoke test that drives a real headless Chromium through the full
upload flow: opens the app, fills the form, uploads a floor plan file, waits
for the AI parse to complete, and saves a full-page screenshot of the results
view. Use this to iterate on lighting-layout rendering without hand-uploading
through the browser every time.

### Setup (one-time)

```
cd scripts
npm install
```

The `postinstall` step downloads the Chromium build Playwright needs.

### Run against the deployed Railway app

```
cd scripts
node e2e-upload-test.mjs --file ~/Downloads/dover-v.pdf --name "Dover V"
```

Screenshots land in `scripts/screenshots/` with a timestamped filename:

```
scripts/screenshots/dover-v-2026-04-15T22-14-03-192Z.png          # full page
scripts/screenshots/dover-v-2026-04-15T22-14-03-192Z.layout.png   # just the layout panel
```

### Run against a local dev server

```
# terminal 1
cd backend && uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev

# terminal 3
cd scripts
node e2e-upload-test.mjs --url http://localhost:5173 --file ./sample.pdf
```

### Flags

| Flag          | Default                                            | Notes                                        |
| ------------- | -------------------------------------------------- | -------------------------------------------- |
| `--file`      | (required)                                         | Path to the floor plan to upload (PDF/PNG/JPG). |
| `--url`       | `https://lightplan-production.up.railway.app`      | App URL to test.                             |
| `--name`      | `Playwright Test`                                  | Project name written into the form.          |
| `--address`   | (empty)                                            | Optional address / lot field.                 |
| `--auth`      | (none)                                             | `user:pass` for HTTP basic auth.              |
| `--out`       | `scripts/screenshots`                              | Where to save screenshots.                   |
| `--headed`    | `false`                                            | Pass `--headed` to watch the browser run.     |
| `--timeout`   | `180`                                              | Seconds to wait for the parse to finish.     |

### Exit codes

- `0` — upload succeeded, screenshot saved.
- `1` — bad arguments.
- `2` — upload or navigation failed; a `.fail.png` screenshot of the failure state is saved next to it.

### Tips

- Keep a reference plan file outside the repo (plans are usually copyrighted) and point `--file` at it.
- If you want to share a run with Claude in chat, drop the `.layout.png` into the message — it's already cropped to the lighting overlay.
- To re-run after a Railway redeploy, just run the same command again — Railway serves a new build and the script will exercise it.
