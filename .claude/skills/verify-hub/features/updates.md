# Updates: the hub from its git repository, the agents from the hub

Fleet > Updates compares what the hub runs with the tip of the branch of its update source (`update_url` and `update_branch` in the hub's `hub.json`) and lists the commits it is behind. "Check for updates" asks the hub to fetch again, and "Update hub" installs the tip after the hub has compiled it and test-started it. A hub with no `update_url` has hub updates off: the section says so and shows the command that turns them on, with no hub buttons. Below, in both cases, one row per Mac shows its agent version against the one the hub hands out. "Update agent" asks that Mac to take no new builds, finish the ones it has, download the new agent and restart. The Mac drawer has the same button, and agents too old to update themselves say to run `cider-build add <mac>` once.

## Sub-features

- `updates-nav` shows, on the Updates entry, a dot when the hub has an update and the number of outdated agents.
- `updates-hub` shows the update source and branch, the installed commit, the latest commit on the branch with its subject and date, the last check, the state and the commits behind. It names no git host.
- `updates-check` asks for a check with "Check for updates", which answers with a toast, and the check time moves forward in `/api/state`.
- `updates-error` shows the hub's error from the last check or update. When it looks like an ssh or auth failure, it adds the hub's public key (`update_ssh_key` + `.pub`) with a Copy button, or, with no key, how to get one.
- `updates-hub-update` enables "Update hub" only when an update is available and the hub is idle, and confirms before calling `POST /hub/update`. The seeded run does not drive it (see Gotchas).
- `updates-off` on a hub with no update source (`update_url` unset or `off`): the hub section says "Hub updates are off", shows `bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>` with a Copy button and has no Check or Update button. `/api/state` has `release.source` null and the hub never checks.
- `updates-agents` lists every Mac with its agent and an action: "Update agent", "updating", "current", or "run cider-build add <mac> once".
- `updates-agent` updates one Mac after a confirmation. Its row goes to "updating", then "current". "Keep it" changes nothing.
- `updates-drawer` marks the agent "(outdated)" in the Mac's drawer and offers "Update agent" there.
- `updates-all` updates every Mac that can update itself after one confirmation.

## How to get to it (user POV)

- Sidebar, then Fleet, then Updates (`#/updates`).
- From a Mac card or any Mac link, the drawer's "Update agent" button.
- The Agent row on a Mac card shows "(outdated)".

## Driving it with drive.mjs

Preconditions:

- A fresh seeded run that passes `doctor`, with no earlier journey that updated agents. Its `hub.json` names the run's local repository as `update_url`. The hub's first check runs 5 s after it starts, and `up` waits for it.
- For `updates-off`, a separate run started with `hubctl.py up --no-updates`, whose `hub.json` has no `update_url`.

- **Nav.** Run `t.nav("/")`. The text of `#nav a[href="#/updates"] .nav-count` includes `hub update available` and `5`.
- **Hub.** Run `t.click('#nav a[href="#/updates"]')`. `#up-hub` shows `Source` with the run's repository path and `· main`, both commits (12 characters each), `Latest on main` with the subject `Panel: show each build's estimated time left`, `update available` and `1 commit behind`. Both `#up-hub` buttons are enabled.
- **Check.** Run `t.click("#up-hub button", "Check for updates")`. A toast reads `Check for updates: checking`, and `/api/state` soon has a larger `release.checked` with `phase` back to `idle`.
- **Refuse.** Find mac-beta's row index in `#up-agents tbody tr`, then run `t.click('#up-agents tbody tr:nth-child(<i>) button', "Update agent")` and `t.click("#confirm-no")`. `/api/state` still has mac-beta with `update` false.
- **Update one.** Repeat with `t.click("#confirm-yes")`. A toast reads `Update mac-beta: updating mac-beta`. The row shows the `updating` badge, then `current`. In `/api/state`, mac-beta's `version` equals `agent`, `update` is false and `state` is `online`.
- **Drawer.** Click mac-epsilon's link in its row. The drawer's Agent row ends in `(outdated)`. Run `t.click("#drawer-body button", "Update agent")` and `t.click("#confirm-yes")`. `(outdated)` goes away and `/api/state` has `agent_current` true.
- **All.** Run `t.click("#up-agents button", "Update all outdated (1)")` and `t.click("#confirm-yes")`. A toast reads `Update all: 1 updating`. Every Mac with `self_update` becomes current. mac-zeta stays outdated and its row says `run cider-build add mac-zeta once`. The nav count drops to 2.
- **Off.** On the `--no-updates` run, `t.nav("/")`, then `t.click('#nav a[href="#/updates"]')`. `#up-hub` reads `Hub updates are off: this hub has no update source.`, has one `.cmd` whose code is `bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>` and whose only button is Copy, and no other button. The nav count shows `5` without `hub update available`. "Update agent" on mac-beta still reaches `current`.
- **Error.** Not in the journey. Move `/tmp/verify-hub/run-<id>/repo` away and click "Check for updates". `#up-hub` shows the git error and, since the seeded hub has no `update_ssh_key`, the note on how to get a key. Move the repository back afterwards.
- **Proof.** `journeys/updates.mjs` takes screenshots of the hub section, the confirmation, the drawer and the final table, and reads every result again from `/api/state`. `journeys/updates-off.mjs` does the same for the off state.

## Gotchas

- Never click "Update hub" on a seeded run. The hub would replace `/tmp/verify-hub/run-<id>/home/bin`, exit, and nothing restarts it. `verification/hub-update.py` proves the hub update with a restart that plays launchd.
- A fake Mac reports the new version on its next heartbeat, so "updating" lasts about 2 s. The journey records it with a MutationObserver instead of a timed screenshot. A real agent stays "updating" until its builds end.
- The section only re-renders when the release state or a Mac's agent fields change, so "Last checked" ticks through `data-ago`, not through re-renders.
- Updating agents changes the seed. Run this journey after the read-only ones, or on its own run.
- `mac-gamma` never sends a heartbeat in the seed, so the hub has never seen it report `self_update`, and its row says to run `cider-build add`.
- Against an older hub through `up --real`, `release` has no `source` key. The panel then shows the hub section as on, without the Source row.
