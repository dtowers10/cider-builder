# Fleet: the Mac cards and their actions

Fleet shows a two-line card per Mac: its name and state badge, then its slots, free RAM, Xcode and what it builds, or the reason it takes no builds with `Why` or `Enable`, plus a note when its agent is outdated. A card opens the Mac's drawer: the reason it takes no builds (if any), the slots field with `Change slots`, `Disable` or `Enable`, `Update agent`, the facts (RAM, Xcode, agent, user, last heartbeat, boot, the jobs it reports, machine details), what it is building, its last 20 jobs and its affinity. The Fleet view also holds the update banner, the Updates section and Add a Mac (see `updates.md` and `cache-and-add.md`). `cider-build status` shows the same fleet as text.

## Sub-features

- `fleet-cards` shows one card per enabled or heartbeating Mac, with a state badge: online, missing tools, no heartbeat, disabled, updating the agent, never scheduled (the hub itself or a Mac in its `exclude` setting), or out of the pool (a Mac the hub's `drain_command` lists).
- `fleet-drawer` opens a Mac's detail with the reason paragraph first, then the actions, the facts, what it builds, its last jobs and its affinity. The Board's `Why` links land here too.
- `fleet-slots` changes the slots after a confirmation. "Keep it" changes nothing. The typed value survives the 2 s poll.
- `fleet-disable` disables a Mac after a confirmation. The slots field locks with "enable it first". The Board shows the builds it still finishes and an `Enable` cell.
- `fleet-enable` enables it again with its previous slots, from the drawer, a card or a Board cell.
- `fleet-cli` shows the same states in `cider-build status`.

## How to get to it (user POV)

- The top bar's Fleet entry, `#/fleet`, or the old `#/macs` and `#macs`, then click a card.
- A Board lane's Mac name, or `Why` in an off cell.
- An alert chip for a lost Mac or missing tools.
- Any Mac link in a table or drawer (`#mac/<label>`).
- `CIDER_BUILD_HUB=<url> bin/cider-build status` in a terminal.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. mac-beta is online with 1 slot and 1 build.

The proven journey is `journeys/fleet.mjs`. It changes mac-beta and restores it, so run it after the read-only journeys.

- **Cards.** Run `t.nav("/#/fleet")`. `#maclist .card` has 5 cards, in label order, with `data-id` set to the label. The badge of mac-alpha reads `online`, mac-epsilon `missing tools`, mac-gamma `no heartbeat` and mac-zeta `disabled`. mac-alpha's text is `mac-alpha online 2/2 slots · 22 GB free · Xcode 16.4 · building demo ios, shop android agent outdated`. mac-epsilon's includes `missing tools · Why`, mac-gamma's `no heartbeat · lost 1 h ago · Why`, mac-zeta's `disabled · Enable` and `agent outdated: run cider-build add mac-zeta once`.
- **Open drawer.** Run `t.click('#maclist a[href="#mac/mac-beta"]')`. `#drawer-title` reads `Mac mac-beta`, the hash is `#/fleet/mac/mac-beta`, `#drawer-body` has `Building here` with `ledger ios`, `Last 20 jobs` and `Affinity`, and no `p.note` (an online Mac needs no reason).
- **Refuse a change.** Run `t.type("#drawer-body input[type=number]", "3")`, `t.click("#drawer-body button", "Change slots")`: `#confirm-title` reads `Change slots on mac-beta` and the body includes `From 1 to 3 slots`. `t.click("#confirm-no")` closes it, `/api/state` still has slots 1 and the field still reads 3.
- **Change slots.** Repeat, then run `t.click("#confirm-yes")`. A toast reads `Slots on mac-beta: mac-beta 3`, `/api/state` has slots 3 and the drawer reads `1 in use of 3`.
- **Disable.** Run `t.click("#drawer-body button", "Disable")`, then `t.click("#confirm-yes")`. A toast reads `Disable mac-beta: running 1`. After the next poll the drawer badge reads `disabled`, the slots input is disabled with `enable it first`, and on the Board `.lane[data-id="mac-beta"]` has one `.cell.job` and a `.cell.off` reading `disabled · Enable`.
- **Enable.** Run `t.click("#drawer-body button", "Enable")`. The body reads `With its previous 3 slots.` Then `t.click("#confirm-yes")`. A toast reads `Enable mac-beta: mac-beta 3` and the badge returns to `online`.
- **Restore.** Set the slots back to 1 with the same steps. `t.click("#drawer-close")` returns focus to the `a[href="#mac/mac-beta"]` card link.
- **CLI.** Run `CIDER_BUILD_HUB=<run url without the trailing slash> bin/cider-build status`. The table lists the same five Macs and states, with the header `MAC STATE SLOTS FREE RAM XCODE`.
- **Proof.** The journey writes `fleet.png`, `slots-confirm.png`, `slots-after.png` and `disable-after.png`, and reads `/api/state` for the slots and the enabled flag.

## Gotchas

- Toasts disappear after 5 s, or 9 s for errors. Assert right after the action, or with `t.waitFor`.
- Each region re-renders only when what it shows changes. The drawer's action row keeps the typed slots across polls; the facts (with the heartbeat age) re-render every poll. Wait for the next 2 s poll before asserting the badge.
- Disabling a Mac with running builds lets them finish, so `used` stays above 0 for a while.
- `mac-zeta` sends heartbeats while disabled. Enabling it makes it take a queued job, which changes the queue for later journeys. The journey only refuses that confirmation.
- Never run these actions through `up --real`. The proxy refuses them, so a test there proves nothing and would only show an error toast.
