---
name: verify-hub
description: Drives the cider-build hub's web panel (bin/cider-build-panel.html served by bin/cider-build-hub) and the `cider-build status` CLI against a disposable, seeded hub on 127.0.0.1, and captures evidence. Use it to prove any change to the panel or to what the hub shows (views, routes, drawer, actions, History filters, cache, Add a Mac, Updates), and to read the real hub safely through a read-only proxy. It does not check the job protocol; that is verify-job-protocol.
metadata:
  internal: true
---

# Verify the hub panel

The user-facing surface is the panel that `bin/cider-build-hub` serves at `/`. A second surface is the client CLI, `bin/cider-build status`. Builds themselves need real Macs and are out of scope here. `verification/hub-smoke.py` covers the build cycle over HTTP, and the `verify-job-protocol` skill covers the protocol.

Everything below runs on Linux with `python3`, `node` (22 or later, for the global `WebSocket`) and `google-chrome`. Paths are relative to the repository root. The helpers are in `.claude/skills/verify-hub/scripts/`.

## Launch

```bash
S=.claude/skills/verify-hub/scripts
python3 $S/hubctl.py up            # optional: --run <id>; --no-updates for a hub with no update source
export VERIFY_HUB_RUN=<id from the READY line>
```

`up` prints `READY run=<id> url=http://127.0.0.1:<port>/ mode=seeded evidence=/tmp/verify-hub/evidence/<id>` when the instance is usable, not just answering. That means the seeded data is visible through the API. Without that line nothing is ready. On failure it exits non-zero and names the log to read.

What `up` starts:
- The real `bin/cider-build-hub` from this checkout, with `CIDER_BUILD_HOME=/tmp/verify-hub/run-<id>/home` and two free ports. A fake `tailscale` on `PATH` names it `verify-hub-<id>` and makes `/join` work on 127.0.0.1 with no tailnet. Other `CIDER_BUILD_*` settings in the environment reach the hub (`CIDER_BUILD_EXCLUDE=my-laptop`, `CIDER_BUILD_CACHE_KEEP=3`). The hub reads the panel from `bin/cider-build-panel.html` on every request, so panel edits show on reload with no restart.
- A fleet process that plays the Macs over the same HTTP calls the agent makes: heartbeats every 2 s, live log lines for every running job, and a fresh queued job with no source whenever the previous one is gone.

Seeded state, which `features/README.md` relies on:

| Mac | Panel state | Slots | Agent (Updates view) |
|---|---|---|---|
| mac-alpha | online | 2/2, building `demo ios` and `shop android` | outdated, can update itself |
| mac-beta | online | 1/1, building `ledger ios` | outdated, can update itself |
| mac-epsilon | missing tools | 0/1 | outdated, can update itself |
| mac-gamma | no heartbeat | 0/2 | outdated, needs `cider-build add` |
| mac-zeta | disabled (but sends heartbeats) | 0/2 | outdated, needs `cider-build add` |
| linux-delta | online, Linux, builds Android only | 1/1, building `scanner android` | outdated, can update itself |

Also seeded: the queue (`scanner android` and `demo android` with source, which wait for linux-delta because Android stays off the Macs while a Linux machine is in the pool, and `shop ios` with no source); 42 finished jobs spread over about 4 days (done, failed with rc 65, cancelled), 2 of them failed in the last 24 h; 4 cache projects with 2 artifacts each; affinity for each project.

For Updates: the hub's `hub.json` names a local repository at `/tmp/verify-hub/run-<id>/repo` as `update_url` (with `--no-updates` it is `off`, and hub updates are off). Its first commit is what `home/bin` holds (this checkout's release files, named in `bin/.commit`), and `main` is one commit ahead with the subject `Panel: show each build's estimated time left`, so the hub shows an update available, 1 commit behind. All machines report agent `2026.10.3`, older than what the hub hands out. A fake Mac asked to update reports the requested version on its next heartbeat; a real agent first waits for its builds to end.

A real hub, read-only:

```bash
python3 $S/hubctl.py up --real [URL]   # this checkout's panel, GETs forwarded to URL (default: what `bin/cider-build hub` prints)
```

The proxy serves the panel with the hub's own CSP code and forwards only `/api/*` and `/poll`. POST, PUT and DELETE get 405 from the proxy and never reach the real hub. Use it to see real data in the new panel. Never click an action expecting it to work there.

Several runs can live side by side, because each has its own home, ports and Chrome profile.

## Doctor

```bash
python3 $S/hubctl.py doctor        # exit 0 = worth driving
```

Read-only. It checks four things:
- Every process of the run is alive and carries the run's marker, so a reused PID is never mistaken for ours.
- The port answers as `https://verify-hub-<id>.example.ts.net:<port>`, which proves it is our hub and not another one on that port.
- The fake Macs sent a heartbeat in the last 10 s.
- The panel served has the same CSP hashes as this checkout's `bin/cider-build-panel.html`.

With `--real` it also checks that the proxy refuses writes. Run it first, and again whenever anything looks off.

## Drive

```bash
node $S/drive.mjs .claude/skills/verify-hub/journeys/navigation.mjs   # optional: --run <id>, --keep-going
```

`drive.mjs` starts its own headless Chrome with a profile inside the run's directory. It loads a journey module that exports `default async (t) => {}` and closes Chrome when the journey ends. Exit 0 means every check passed and there were no console or CSP errors.

The `t` object passed to a journey has these helpers:

| Helper | What it does |
|---|---|
| `t.nav("/#/history")` | A cold load in a fresh document, like opening a link in a new tab. Change the hash with `t.click` or `t.ev('location.hash = "#/macs"')` instead when you want in-app navigation. |
| `t.click(selector, text?)` | A real mouse click at the element's centre. `text` picks, among the matches, the one whose trimmed text equals it, e.g. `t.click("#drawer-body button", "Disable")`. |
| `t.clickAt(x, y)` | A real mouse click at a viewport point, for what `t.click` cannot hit at an element's centre, such as the drawer's backdrop: at 1280 px the drawer (`min(820px, 100vw)`) covers the backdrop's centre, so click at `(100, 400)`. |
| `t.press("Tab" \| "Enter" \| "Escape" \| "ArrowDown" \| "ArrowUp")` | A real key event to the focused element |
| `t.type(selector, text)` | Click, select the field's content, then insert text |
| `t.select(selector, value)` | Focus a native `<select>` and move with the arrow keys until it holds `value` |
| `t.size(w, h)` | Viewport size. Use 390x800 for the narrow layout (the breakpoint is 860 px). |
| `t.back()`, `t.forward()` | Browser history |
| `t.ev(expr)`, `t.waitFor(expr, ms)` | Read page state. Use them for assertions, never to perform the user's action. |
| `t.sleep(ms)` | Wait a fixed time. Prefer `t.waitFor`; use it only to let a timer tick. |
| `t.check(name, ok, detail?)` | Record a check. The first failure stops the journey unless `--keep-going`. |
| `t.shot(name)`, `t.aria(name)` | A screenshot, and an ARIA tree as text |

Stable handles in the panel:
- **Sidebar.** Links are `#nav a[href="#/<view>"]`, with `<view>` in `overview, macs, add, updates, builds, history, cache`. The current one has `aria-current="page"`.
- **Views.** Each view is a `main > section#view-<view>`, and only one is visible. Its heading is the section's `h2`.
- **Drawer.** `#drawer`, with `#drawer-title` and `#drawer-close`.
- **Confirmation dialog.** `#confirm`, with the buttons `#confirm-yes` and `#confirm-no` ("Keep it").
- **Toasts.** `#toasts .toast`.

Each `features/*.md` file has the rest. Write a new journey next to `navigation.mjs` for any feature you prove, and keep it.

The CLI drives against the same instance:

```bash
CIDER_BUILD_HUB=$(python3 -c 'import json,os;print(json.load(open("/tmp/verify-hub/run-%s/state.json" % os.environ["VERIFY_HUB_RUN"]))["url"].rstrip("/"))') bin/cider-build status
```

If the user wants to watch, the same selectors work with the T3 browser preview tools (`preview_act` with a CSS `selector`, `preview_evaluate`). Reuse one tab, and close it when you finish.

## Evidence

Each `drive.mjs` run writes to `/tmp/verify-hub/evidence/<id>/<journey>-<HHMMSS>/`:
- `journal.txt`, with every action, every `OK`/`FAIL` check and the final `RESULT pass|fail`;
- the `.png` and `.aria.txt` files the journey asked for;
- `failure.png` if a step threw.

Quote the `RESULT` line and the failing checks in the report, and attach the screenshots that show the action and the state it produced.

Proof standards:
- Act the way a user does, through `t.click`, `t.press`, `t.type` and `t.select`. Use `t.ev` only to read state. Never call the panel's functions or the hub's routes to perform an action you claim the user can do.
- Capture the action and the resulting state, not only the final screen. For a mutation, also read the stored value a second way: `/api/state`, `bin/cider-build status`, or reopening the drawer after a refresh.
- `aria-current` does not appear in Chrome's CDP accessibility tree. Assert it from the DOM, with `#nav [aria-current="page"]`.
- A pass on the seeded hub does not prove the real fleet. Say which instance each claim came from.

## Cleanup

```bash
python3 $S/hubctl.py down          # optional: --run <id>; `list` shows runs still alive
```

`down` kills only the processes the run started: the hub, the fleet or the proxy, and a Chrome left behind by a crashed journey. It finds them by the PIDs stored in the run's `state.json` and checks the run marker in their environment. It never kills by name. Then it deletes `/tmp/verify-hub/run-<id>/` and prints where the evidence is. It never touches `/tmp/verify-hub/evidence/`. Run `down` after every failed attempt too, so ports and processes do not pile up.

## Gotchas

- **Chrome hangs on every network request** (blank page, `Page.navigate: no answer from Chrome in 15 s`). In a desktop session whose keyring is locked, Chrome waits for the cookie key over D-Bus before opening any connection. `drive.mjs` passes `--password-store=basic` for that reason. If you launch Chrome yourself, pass it too, or unset `DBUS_SESSION_BUS_ADDRESS`.
- **Hash changes move focus.** In-app navigation moves focus to the view's heading. The next Tab continues from there, not from the sidebar. Use `t.nav` (a cold load) before checking Tab order from the top of the page.
- **`#job/<id>` and `#mac/<label>` open over the current view.** On a cold load the current view is Overview. In-app, it is whatever is shown. Either way the panel rewrites the hash to `#/<view>/<kind>/<id>`.
- **No "out of the pool" Mac in the seed.** The hub learns that state from its `drain_command`, and the seed has none. Check that counter against a real hub that has one with `up --real`, read-only.
- **The queued job with no source is replaced, not kept.** The hub cancels it after 120 s (`SOURCE_TTL`), and the fleet submits a new one with a new id. Don't hard-code its id.
- **Never click "Update hub" on a seeded run.** It would replace `home/bin` and exit the hub, and nothing restarts it. `verification/hub-update.py` proves the hub update, with a restart that plays launchd.
- **Actions change the seed.** Cancelling a building job frees a slot, the hub assigns a queued job, and the fleet starts building it. Run mutation journeys last, or start a fresh run.
- **Never use `pkill -f <pattern>` in this environment.** The pattern also matches the shell that runs it. Use `hubctl.py down`.

## Helpers

- `scripts/hubctl.py`: `up [--real [URL] | --no-updates] [--run ID]`, `doctor`, `down`, `list`. Python 3.9 or later, standard library only.
- `scripts/drive.mjs`: `node drive.mjs [--run ID] [--keep-going] <journey.mjs>`
- `journeys/navigation.mjs`: the proven journey for `features/navigation.md`.
- `journeys/updates.mjs`: the proven journey for `features/updates.md`. It updates agents, so run it after the read-only journeys.
- `journeys/updates-off.mjs`: the same feature on a run started with `up --no-updates`.
- `features/README.md`: the feature map. Read it before driving.
