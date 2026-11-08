# Sidebar navigation and routes

The panel has a fixed sidebar on the left. Each entry opens one view on its own, at its own hash URL, which works with Back and Forward, reload and direct links. The detail drawer for a job or a Mac opens over whichever view is shown. Old single-page links keep working. At 860 px or less the sidebar becomes a top bar with a Menu button.

## Sub-features

- `nav-click` opens each of the seven views from the sidebar, marks it with `aria-current="page"` and sets the tab title to `<Label> · Cider Builder`.
- `nav-keyboard` reaches the sidebar with Tab, shows a focus ring, opens a view with Enter and moves focus to the view's heading.
- `nav-url` restores the view (and the drawer, if any) from a direct link or a reload. An empty or unknown hash lands on Overview; an unknown one is rewritten to `#/overview`.
- `nav-back` moves between views with Back and Forward.
- `nav-legacy` maps `#macs`, `#trabajos`, `#historial`, `#cache` and `#unir` to their views and rewrites the hash to `#/<view>`.
- `nav-drawer` opens `#job/<id>` or `#mac/<label>` over the current view, rewrites it to `#/<view>/<kind>/<id>`, and closes it with Escape (unless the confirmation dialog is open), Close, a click on the backdrop (`#scrim`) or Back while keeping the view. Close goes Back only when the entry before is that same view with no drawer (a plain in-page open), so Forward reopens the drawer. In every other case (a cold load or reload, a drawer link pasted from another view, a link followed inside the drawer) Close replaces the address with `#/<view>`.
- `nav-counts` shows live counts in the sidebar as coloured dots: building (blue) and queued (grey) on Running & queue, lost (red) and out-of-pool (violet) Macs on Macs, and on Updates a violet dot when the hub has an update plus the number of outdated agents (violet). Each one is hidden at zero.
- `nav-narrow` collapses the sidebar behind Menu. Escape, picking an item, any route change, or pressing Menu again closes it.

## How to get to it (user POV)

- Click an entry in the sidebar: Overview; Fleet, with Macs, Add a Mac and Updates; Builds, with Running & queue, History and Cache & affinity.
- Press Tab from the top of the page, then Enter.
- Open a URL such as `http://<hub>/#/history` or `http://<hub>/#/history/job/<id>`, or reload one.
- Click any job or Mac link or row in a view or in the drawer (`#job/<id>`, `#mac/<label>`).
- Follow an old anchor: `#macs`, `#trabajos`, `#historial`, `#cache`, `#unir`.
- From Overview, click "N queued" (`#ov-queued`) or "All failures in History" (`#ov-all-failures`).
- The panel is also served at `http://<hub>/panel`.
- Use the browser's Back and Forward.
- On a narrow screen, press Menu.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. Mutations from an earlier journey in the same run don't matter here.

The proven journey is `journeys/navigation.mjs`. Run it with `node .claude/skills/verify-hub/scripts/drive.mjs .claude/skills/verify-hub/journeys/navigation.mjs`. It runs 44 checks and should end in `RESULT pass`. Step by step:

- **Land.** Run `t.nav("/")`. The shown section is `view-overview` and `#nav [aria-current="page"]` has `href="#/overview"`.
- **Click each view.** Run `t.click('#nav a[href="#/macs"]')`, and so on for every view. Exactly one `main > section` is visible, the hash is `#/macs`, and `document.title` ends with `· Cider Builder`.
- **Back and Forward.** After clicking History and then Cache, run `t.back()`, which shows History, then `t.forward()`, which shows Cache.
- **Keyboard.** Run `t.nav("/#/overview")`, then `t.press("Tab")` twice. The focused element is `#nav a[href="#/macs"]` and matches `:focus-visible`. Then run `t.press("Enter")`. The Macs view shows and `document.activeElement` is its `H2 Macs`.
- **Legacy anchors.** Run `t.ev('location.hash = "#trabajos"')`. The view is builds and the hash is `#/builds`. The other anchors map to macs, history, cache and add.
- **Drawer over every view.** On each view, run `t.ev('location.hash = "#mac/mac-gamma"')`. `#drawer` is visible, `#drawer-title` reads `Mac mac-gamma`, the hash is `#/<view>/mac/mac-gamma` and the view is unchanged. Then run `t.press("Escape")`. The drawer closes and the hash is `#/<view>`.
- **Close never changes the view or reopens a drawer.** Run `t.nav("/#/overview")`, then `t.ev('location.hash = "#/history/mac/mac-alpha"')` and `t.press("Escape")`. History stays, the drawer is closed and the hash is `#/history`. Then, from a cold `#/overview`, run `t.ev('location.hash = "#job/<id>"')` for a history job with a worker, `t.click('#drawer a[href^="#mac/"]')` and `t.click("#drawer-close")`. The drawer closes and the hash is `#/overview`.
- **Unknown hash and backdrop.** From a cold `#/overview`, run `t.ev('location.hash = "#/nope"')`. Overview shows and the hash is `#/overview`. Open mac-gamma's card from Macs, then run `t.clickAt(100, 400)` on the backdrop beside the drawer. The drawer closes and the hash is `#/macs`. `t.click("#scrim")` would land on the drawer, which covers the backdrop's centre.
- **Close goes Back.** From a cold `#/overview`, open `#mac/mac-gamma`, click Close, then run `t.forward()`. The drawer for mac-gamma is back at `#/overview/mac/mac-gamma`.
- **Cold links.** Run `t.nav("/#job/<first id of /api/history>")`. Overview shows with the drawer titled `Job <id>`. Then run `t.nav("/#/cache/mac/mac-alpha")`. Cache shows with the drawer for mac-alpha. Then run `t.click("#drawer-close")`, which leaves the hash at `#/cache`.
- **Narrow.** Run `t.size(390, 800)`, then `t.nav("/#/overview")`. `#nav` has `display: none`. Run `t.click("#menu-btn")`, which sets `aria-expanded="true"`. Run `t.press("Escape")`, which closes the menu and puts focus on `#menu-btn`. Pick History from the reopened menu: it opens and the menu closes. Press Menu twice: it opens, then closes.
- **Counts (`nav-counts`, asserted by `journeys/builds.mjs`, `macs.mjs` and `updates.mjs`, not by this journey).** On the seed, `#nav a[href="#/builds"] .nav-count` reads `4 building3 queued` as text (a blue and a grey dot on screen), with the labels visually hidden. `#nav a[href="#/macs"] .nav-count` reads `1 lost`. `#nav a[href="#/updates"] .nav-count` reads `hub update available6 agents outdated`. Cancel the queued `demo android` (see `builds.md`) and, within one 2 s poll, the queued count drops to 2.
- **Proof.** The journey writes `view-<view>.png` for each view, `drawer-over-history.png`, `narrow-menu-open.png`, `sidebar-overview.aria.txt` and `narrow-menu-open.aria.txt`.

## Gotchas

- Whether Close may go Back is stored on the history entry (`history.state.back`), so it survives Back and Forward. A reload records `false`, so Close after a reload replaces the address.
- In-app changes to a different view move focus to its heading, unless a drawer is open. Tab after that continues inside the view. Start keyboard checks with a cold `t.nav`.
- `t.nav` to a URL that differs from the current one only in the hash is still a cold load in `drive.mjs`. In the T3 preview, `preview_navigate` to the same path is an in-app hash change. Use another path (`/panel`) or `location.reload()` there.
- `aria-current` is missing from Chrome's CDP accessibility tree. Assert it from the DOM.
- The seed has no `drain_command`, so no Mac is out of the pool and the violet counter on Macs only shows on a hub that has one, such as a real hub through `up --real`.
- History filters live in the page, not in the URL. They survive the 2 s refresh but not a reload. That is by design.
