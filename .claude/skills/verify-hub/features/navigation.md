# Top bar navigation, routes, alerts and counts

The panel has a top bar: the hub's name, four entries (Board, History, Fleet, Cache) with live counts, the alert chips and the connection dot. Each entry opens one view on its own, at its own hash URL, which works with Back and Forward, reload and direct links. The detail drawer for a job or a Mac opens over whichever view is shown. Old routes and anchors keep working as aliases. Below 860 px the nav collapses behind a Menu button and the chips fold into one.

## Sub-features

- `nav-click` opens each of the four views from the top bar, marks it with `aria-current="page"` and sets the tab title to `<Label> · Cider Builder`.
- `nav-keyboard` reaches the top bar with Tab, shows a focus ring, opens a view with Enter and moves focus to the view's heading.
- `nav-url` restores the view (and the drawer, if any) from a direct link or a reload. An empty or unknown hash lands on Board.
- `nav-back` moves between views with Back and Forward.
- `nav-legacy` maps the old routes and anchors to their views and rewrites the hash to `#/<view>`: `#/overview`, `#/builds` and `#trabajos` to Board; `#historial` to History; `#/macs`, `#macs`, `#/add`, `#unir` and `#/updates` to Fleet; `#cache` to Cache.
- `nav-target` scrolls to and focuses a heading inside Fleet for `#/add` and `#unir` (`h3#fleet-add`) and `#/updates` (`h3#fleet-updates`), from the `.jump` links at the top of Fleet too. The hash becomes `#/fleet`.
- `nav-drawer` opens `#job/<id>` or `#mac/<label>` over the current view, rewrites it to `#/<view>/<kind>/<id>`, and closes it with Escape, Close or Back while keeping the view. Close goes Back only when the entry before is that same view with no drawer (a plain in-page open), so Forward reopens the drawer. In every other case (a cold load or reload, a drawer link pasted from another view, a link followed inside the drawer) Close replaces the address with `#/<view>`.
- `nav-focus` moves focus to `#drawer-close` when a drawer opens in-app, and back to the link that opened it (or the same link after a re-render, or the view's `h2`) when it closes.
- `nav-counts` shows live counts in the top bar as coloured dots: building (blue) and queued (grey) on Board, failed in the last 24 h (red) on History, what needs attention on Fleet (the number of alerts, with the worst alert's colour) and the cache size on Cache. Each one is hidden at zero.
- `nav-alerts` shows one chip per alert in `#summary`, worst first: a lost Mac (red, with how long ago), a failed agent update (red), a hub update error (red), missing tools (yellow), and one violet chip for a hub update and the outdated agents. Each chip links to where it is fixed: the Mac's drawer or Fleet's Updates section. With nothing to show it reads `No alerts`.
- `nav-narrow` collapses the nav behind Menu and folds the chips into one `<n> alerts` chip that links to Fleet. Escape or picking an item closes the menu.

## How to get to it (user POV)

- Click an entry in the top bar: Board, History, Fleet or Cache.
- Click an alert chip in the top bar.
- Press Tab from the top of the page, then Enter.
- Open a URL such as `http://<hub>/#/history` or `http://<hub>/#/history/job/<id>`, or reload one.
- Follow an old link: `#job/<id>`, `#mac/<label>`, `#/overview`, `#/builds`, `#/macs`, `#/add`, `#/updates`, `#macs`, `#trabajos`, `#historial`, `#cache`, `#unir`.
- Use the browser's Back and Forward.
- On a narrow screen, press Menu.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`, with no earlier journey in the same run: the counts and chips are the seed's.

The proven journey is `journeys/navigation.mjs`. Run it with `node .claude/skills/verify-hub/scripts/drive.mjs .claude/skills/verify-hub/journeys/navigation.mjs`. It should end in `RESULT pass`. Step by step:

- **Land.** Run `t.nav("/")`. The shown section is `view-board` and `#nav [aria-current="page"]` has `href="#/board"`.
- **Counts.** `#nav a[href="#/board"] .nav-count` reads `3 building3 queued` as text (a blue and a grey dot on screen, labels visually hidden), `…"#/history"…` reads `2 failed in the last 24 h`, and `…"#/fleet"…` reads `3 need attention`.
- **Alerts.** The `#summary a` chips (without `.alerts-n`) read `mac-gamma lost 1 h ago`, `mac-epsilon missing tools` and `Hub update · 5 agents outdated`. Run `t.click('#summary a[href="#mac/mac-gamma"]')`: the drawer `Mac mac-gamma` opens over Board.
- **Click each view.** Run `t.click('#nav a[href="#/history"]')`, and so on for every view. Exactly one `main > section` is visible, the hash is `#/history`, and `document.title` ends with `· Cider Builder`.
- **Back and Forward.** After clicking Fleet and then Cache, run `t.back()`, which shows Fleet, then `t.forward()`, which shows Cache.
- **Keyboard.** Run `t.nav("/#/board")`, then `t.press("Tab")` twice. The focused element is `#nav a[href="#/history"]` and matches `:focus-visible`. Then run `t.press("Enter")`. History shows and `document.activeElement` is its `H2 History`.
- **Old routes and anchors.** Run `t.ev('location.hash = "#trabajos"')`. The view is board and the hash is `#/board`. The others map as listed under `nav-legacy`.
- **Targets.** On Fleet, run `t.click('.jump a[href="#/add"]')`. The hash is `#/fleet` and `document.activeElement.id` is `fleet-add`. The `Updates` link focuses `fleet-updates`.
- **Drawer over every view.** On each view, run `t.ev('location.hash = "#mac/mac-gamma"')`. `#drawer` is visible, `#drawer-title` reads `Mac mac-gamma`, the hash is `#/<view>/mac/mac-gamma` and the view is unchanged. Then run `t.press("Escape")`. The drawer closes and the hash is `#/<view>`.
- **Close never changes the view or reopens a drawer.** Run `t.nav("/#/board")`, then `t.ev('location.hash = "#/history/mac/mac-alpha"')` and `t.press("Escape")`. History stays, the drawer is closed and the hash is `#/history`. Then, from a cold `#/board`, run `t.ev('location.hash = "#job/<id>"')` for a history job with a worker, `t.click('#drawer a[href^="#mac/"]')` and `t.click("#drawer-close")`. The drawer closes and the hash is `#/board`.
- **Close goes Back.** From a cold `#/board`, open `#mac/mac-gamma`, click Close, then run `t.forward()`. The drawer for mac-gamma is back at `#/board/mac/mac-gamma`.
- **Focus.** From a cold `#/board`, run `t.click('#board-lanes a[href^="#job/"]')`. `document.activeElement.id` is `drawer-close`. Run `t.press("Escape")`: the active element is a link with the same `href` as the one clicked.
- **Cold links.** Run `t.nav("/#job/<first id of /api/history>")`. Board shows with the drawer titled `Job <id>`. Then run `t.nav("/#/cache/mac/mac-alpha")`. Cache shows with the drawer for mac-alpha. Then run `t.click("#drawer-close")`, which leaves the hash at `#/cache`.
- **Narrow.** Run `t.size(390, 800)`. On a cold `#/board`, `#/history` and `#/fleet`, `document.documentElement.scrollWidth` is at most 390. `#nav` has `display: none`, `#summary .alerts-n` reads `3 alerts` and is displayed, and the per-alert chips are not. Run `t.click("#menu-btn")`, which sets `aria-expanded="true"`. Run `t.press("Escape")`, which closes the menu and puts focus on `#menu-btn`. Pick History from the reopened menu: it opens and the menu closes.
- **Proof.** The journey writes `view-<view>.png` for each view, `drawer-over-history.png`, `narrow-menu-open.png`, `bar-board.aria.txt` and `narrow-menu-open.aria.txt`.

## Gotchas

- Whether Close may go Back is stored on the history entry (`history.state.back`), so it survives Back and Forward. A reload records `false`, so Close after a reload replaces the address.
- In-app hash changes to a view move focus to its heading. Tab after that continues inside the view. Start keyboard checks with a cold `t.nav`. Opening a drawer in-app moves focus to Close instead.
- `t.nav` to a URL that differs from the current one only in the hash is still a cold load in `drive.mjs`. In the T3 preview, `preview_navigate` to the same path is an in-app hash change. Use another path (`/panel`) or `location.reload()` there.
- `aria-current` is missing from Chrome's CDP accessibility tree. Assert it from the DOM.
- The seed has no `drain_command`, so no Mac is out of the pool. The `refused` state (an online Mac that is the hub or in its `exclude` setting) needs `CIDER_BUILD_EXCLUDE=<a seeded label>` at `up`.
- The Fleet count is the number of alerts, so it drops as agents update or Macs come back. Read it before any mutation journey.
- History filters live in the page, not in the URL. They survive the 2 s refresh but not a reload. That is by design.
