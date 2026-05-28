# WH40K Combat Calculator — PWA Setup

## Files in this folder
- `wh40k_combat_calc.html` — the app
- `manifest.json` — PWA metadata
- `sw.js` — service worker (offline support + update handling)
- `icon-192.png` / `icon-512.png` — app icons

---

## Hosting on GitHub Pages (free)

1. Create a new repo on GitHub (e.g. `wh40k-calc`)
2. Upload all 5 files to the repo root
3. Go to **Settings → Pages → Source → Deploy from branch → main → / (root)**
4. Wait ~1 minute, your app will be live at:
   `https://YOUR-USERNAME.github.io/wh40k-calc/wh40k_combat_calc.html`

---

## Installing as an app

**iPhone/iPad:**
1. Open the URL in Safari
2. Tap the Share button → **Add to Home Screen**
3. Tap Add — it installs like a native app, works offline

**Android:**
1. Open the URL in Chrome
2. Tap the menu → **Add to Home Screen** (or Chrome will prompt automatically)

**Desktop (Chrome/Edge):**
1. Open the URL
2. Click the install icon in the address bar (or menu → Install app)

---

## Pushing updates

Just update `wh40k_combat_calc.html` in the repo (drag-and-drop in GitHub's web UI, or `git push`).

The service worker will detect the change next time a user opens the app and automatically serve the new version. Users don't need to do anything.

**To force immediate update on all devices:**
Open `sw.js` and change `wh40k-calc-v1` to `wh40k-calc-v2` (or any new string). This invalidates the old cache and forces every client to download fresh files on next open.

---

## Saved loadouts

Loadouts are stored in the browser's `localStorage`. They persist across sessions on the same device/browser but don't sync between devices. If a user clears their browser data, saves are lost.

For cross-device sync, a future enhancement would be to add export/import of loadouts as JSON.
