# Macs and their actions

The Macs view shows a card per Mac with its state, slot and RAM meters, Xcode, agent version, user, last heartbeat and machine details. A card opens the Mac's drawer, which lists what it is building, its last 20 jobs and its affinity. The drawer is also where the user changes the slots, disables the Mac or enables it again, each after a confirmation. `cider-build status` shows the same fleet as text.

## Sub-features

- `macs-cards` shows one card per enabled or heartbeating Mac, with a state badge: online, missing tools, no heartbeat or disabled (and out of the pool, on a hub whose `drain_command` lists the Mac).
- `macs-drawer` opens a Mac's detail with its building jobs, last jobs and affinity.
- `macs-slots` changes the slots after a confirmation. "Keep it" changes nothing.
- `macs-disable` disables a Mac after a confirmation. The slots field locks with "enable it first".
- `macs-enable` enables it again with its previous slots.
- `macs-cli` shows the same states in `cider-build status`.

## How to get to it (user POV)

- Sidebar, then Macs, then click a card.
- Overview, then the Fleet table, then click a row or the Mac link.
- Any Mac link in a table or drawer (`#mac/<label>`).
- `CIDER_BUILD_HUB=<url> bin/cider-build status` in a terminal.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. mac-beta is online with 1 slot and 1 build.

- **Cards.** Run `t.nav("/#/macs")`. `#maclist .card` has 5 cards. The badge text of mac-epsilon reads `missing tools`, mac-gamma `no heartbeat` and mac-zeta `disabled`.
- **Open drawer.** Run `t.click('#maclist a.card[href="#mac/mac-beta"]')`. `#drawer-title` reads `Mac mac-beta` and the hash is `#/macs/mac/mac-beta`.
- **Refuse a change.** Run `t.type("#drawer-body input[type=number]", "3")`, `t.click("#drawer-body button", "Change slots")` and `t.click("#confirm-no")`. `#confirm` closes, and `/api/state` still has slots 1 for mac-beta.
- **Change slots.** Repeat, then run `t.click("#confirm-yes")`. A toast reads `Slots on mac-beta: mac-beta 3`, and `/api/state` has slots 3.
- **Disable.** Run `t.click("#drawer-body button", "Disable")`, then `t.click("#confirm-yes")`. A toast reads `Disable mac-beta: running 1`. After the next poll the drawer badge reads `disabled` and the slots input is disabled.
- **Enable.** Run `t.click("#drawer-body button", "Enable")`, then `t.click("#confirm-yes")`. A toast reads `Enable mac-beta: mac-beta 3` and the badge returns to `online`.
- **Restore.** Set the slots back to 1 with the same steps.
- **CLI.** Run `CIDER_BUILD_HUB=<run url without the trailing slash> bin/cider-build status`. The table lists the same five Macs and states, with the header `MAC STATE SLOTS FREE RAM XCODE`.
- **Proof.** Take `t.shot` of the confirm dialog and of the drawer after each action. Read `/api/state` for the slots and the enabled flag.

## Gotchas

- Toasts disappear after 5 s, or 9 s for errors. Assert right after the action, or with `t.waitFor`.
- The drawer re-renders its action row only when enabled, slots or used change. Wait for the next 2 s poll before asserting the badge.
- Disabling a Mac with running builds lets them finish, so `used` stays above 0 for a while.
- `mac-zeta` sends heartbeats while disabled. Enabling it makes it take a queued job, which changes the queue for later journeys.
- Never run these actions through `up --real`. The proxy refuses them, so a test there proves nothing and would only show an error toast.
