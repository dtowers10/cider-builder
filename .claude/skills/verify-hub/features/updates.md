# Updates: the hub from its git repository, the agents from the hub

Fleet's banner and its Updates section update the hub from a git repository and each Mac's agent from the hub. The banner, above the Mac cards, appears when there is something to do: `Hub update available · <commit> <subject>` with `Update hub`, and `<n> agents outdated · the hub hands out <agent>` with `Update all outdated (<k>)`, where `k` counts the Macs that can update themselves. The Updates section compares what the hub runs with the tip of the branch of its update source (`update_url` and `update_branch` in the hub's `hub.json`), shows the branch's changelog (its last 30 changes, newest first, each marked installed or pending; a GitHub merge or squash shows as its PR's title and number) and has `Check for updates`. A hub with no `update_url` has hub updates off: the section says so and shows the command that turns them on, with no hub buttons. Each Mac card notes an outdated agent, and the Mac's drawer has `Update agent`; agents too old to update themselves say to run `cider-build add <mac>` once.

## Sub-features

- `updates-nav` shows one violet chip in the top bar for a hub update and the number of outdated agents (`Hub update · 5 agents outdated`), which opens Fleet at its Updates section, and counts it in Fleet's `need attention` number.
- `updates-banner` shows the hub update row with `Update hub` (disabled while the hub is checking, updating or restarting, with the phase text) and the agents row with `Update all outdated (k)` (disabled at 0). Each row renders only when there is something to do.
- `updates-hub` shows the update source and branch, the installed commit, the latest commit on the branch with its subject and date, the last check, the state, and the changelog with the changes not installed yet. It names no git host.
- `updates-changelog` lists every change on the branch, not only the ones the hub lacks: the new one marked pending and the installed one marked installed.
- `updates-check` asks for a check with "Check for updates", which answers with a toast, and the check time moves forward in `/api/state`.
- `updates-error` shows the hub's error from the last check or update, with a red `hub update error` chip in the top bar. When it looks like an ssh or auth failure, it adds the hub's public key (`update_ssh_key` + `.pub`) with a Copy button, or, with no key, how to get one.
- `updates-hub-update` enables "Update hub" in the banner only when an update is available and the hub is idle, and confirms before calling `POST /hub/update`. The seeded run does not drive it (see Gotchas).
- `updates-off` on a hub with no update source (`update_url` unset or `off`): the Updates section says "Hub updates are off", shows `bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>` with a Copy button and has no Check or Update button; the banner has no hub row. `/api/state` has `release.source` null and the hub never checks.
- `updates-agents` notes on each card `agent outdated`, `updating the agent`, `agent update failed: <error>` or `agent outdated: run cider-build add <mac> once`. A current agent has no note.
- `updates-agent` updates one Mac from its drawer after a confirmation. Its card badge goes to `updating the agent`, then the note disappears. "Keep it" changes nothing.
- `updates-drawer` marks the agent "(outdated)" in the Mac's drawer facts and offers "Update agent" in its action row.
- `updates-all` updates every Mac that can update itself after one confirmation, from the banner.

## How to get to it (user POV)

- The violet chip in the top bar, or Fleet's `Updates` jump link, `#/updates` (both land on `h3#fleet-updates`), or the top bar's Fleet entry.
- A Mac card (its note), then the drawer's "Update agent" button.

## Driving it with drive.mjs

Preconditions:

- A fresh seeded run that passes `doctor`, with no earlier journey that updated agents. Its `hub.json` names the run's local repository as `update_url`. The hub's first check runs 5 s after it starts, and `up` waits for it.
- For `updates-off`, a separate run started with `hubctl.py up --no-updates`, whose `hub.json` has `update_url` off.

- **Nav.** Run `t.nav("/")`. `#summary a[href="#/updates"]` reads `Hub update · 5 agents outdated`. Run `t.click('#summary a[href="#/updates"]')`: the hash is `#/fleet` and `document.activeElement.id` is `fleet-updates`.
- **Hub.** `#up-hub` shows `Source` with the run's repository path and `· main`, both commits (12 characters each), `Latest on main` with the subject `Panel: show each build's estimated time left`, `update available` and `1 change not installed yet`. The changelog table has two rows: the new commit, pending, and the installed one, installed. Its `Check for updates` button is enabled.
- **Banner.** `#fleet-banner` reads `Hub update available · <commit> <subject>` and `5 agents outdated · the hub hands out <agent>`, and `#fleet-banner button` are `Update hub` and `Update all outdated (3)`, both enabled.
- **Check.** Run `t.click("#up-hub button", "Check for updates")`. A toast reads `Check for updates: checking`, and `/api/state` soon has a larger `release.checked` with `phase` back to `idle`.
- **Refuse.** Run `t.click('#maclist a[href="#mac/mac-beta"]')`, then `t.click("#drawer-body button", "Update agent")` and `t.click("#confirm-no")`. `/api/state` still has mac-beta with `update` false.
- **Update one.** Repeat with `t.click("#confirm-yes")`. A toast reads `Update mac-beta: updating mac-beta`. The card `#maclist .card[data-id="mac-beta"]` shows the `.b-updating` badge, then loses its `outdated` note, and the drawer loses `(outdated)`. In `/api/state`, mac-beta's `version` equals `agent`, `update` is false and `state` is `online`.
- **Drawer.** Close, then open mac-epsilon's card. The drawer's Agent fact ends in `(outdated)`. Run `t.click("#drawer-body button", "Update agent")` and `t.click("#confirm-yes")`. `(outdated)` goes away and `/api/state` has `agent_current` true.
- **All.** Close. Run `t.click("#fleet-banner button", "Update all outdated (1)")` and `t.click("#confirm-yes")`. A toast reads `Update all: 1 updating`. Every Mac with `self_update` becomes current. mac-zeta stays outdated and its card says `run cider-build add mac-zeta once`. The chip reads `Hub update · 2 agents outdated` and the banner's button reads `Update all outdated (0)`, disabled.
- **Off.** On the `--no-updates` run, `t.nav("/")`: the chip reads `5 agents outdated`. `t.click('#nav a[href="#/fleet"]')`: `#up-hub` reads `Hub updates are off: this hub has no update source.`, has one `.cmd` whose code is `bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>` and whose only button is Copy; the banner has only the agents row. "Update agent" on mac-beta from its drawer still clears its note.
- **Error.** Not in the journey. Move `/tmp/verify-hub/run-<id>/repo` away and click "Check for updates". `#up-hub` shows the git error, the top bar a `hub update error` chip and, since the seeded hub has no `update_ssh_key`, the note on how to get a key. Move the repository back afterwards.
- **Proof.** `journeys/updates.mjs` takes screenshots of the Updates section, the confirmation, the drawer and the final cards, and reads every result again from `/api/state`. `journeys/updates-off.mjs` does the same for the off state.

## Gotchas

- Never click "Update hub" on a seeded run. The hub would replace `/tmp/verify-hub/run-<id>/home/bin`, exit, and nothing restarts it. `verification/hub-update.py` proves the hub update with a restart that plays launchd.
- A fake Mac reports the new version on its next heartbeat, so "updating" lasts about 2 s. The journey records it with a MutationObserver on `#maclist` instead of a timed screenshot. A real agent stays "updating" until its builds end.
- Each card re-renders only when what it shows changes, so "Last checked" in the Updates section ticks through `data-ago`, not through re-renders.
- Updating agents changes the seed. Run this journey after the read-only ones, or on its own run.
- `mac-gamma` never sends a heartbeat in the seed, so the hub has never seen it report `self_update`, and its card says to run `cider-build add`.
- Against an older hub through `up --real`, `release` has no `source` key. The panel then shows the Updates section as on, without the Source row.
