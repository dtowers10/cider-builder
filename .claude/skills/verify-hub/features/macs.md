# Macs and their actions

The Macs view shows a card per builder machine (Mac or Linux) with its state, slot and RAM meters, what it builds (`iOS, Android`, `Android (Linux)` or `nothing yet`), Xcode when it reports one, agent version, user, last heartbeat and machine details (macOS version, or the Linux distribution). A card opens the Mac's drawer, which lists what it is building, its last 20 jobs and its affinity. The drawer is also where the user changes the slots, disables the Mac or enables it again, or updates its agent, each after a confirmation. The panel has no Remove action: the Disable dialog names `cider-build remove <mac>`, to run from a client. `cider-build status` shows the same fleet as text.

## Sub-features

- `macs-cards` shows one card per enabled or heartbeating Mac, with a state badge: online, missing tools, no heartbeat, disabled or updating the agent (and out of the pool, on a hub whose `drain_command` lists the Mac).
- `macs-builds` shows a Builds row on cards and in the drawer. A Linux machine reads `Android (Linux)`, has no Xcode row and shows its distribution. A machine without tools reads `nothing yet`.
- `macs-count` shows lost and out-of-pool machines on the sidebar Macs entry, and `Macs online x/y` in the header.
- `macs-drawer` opens a Mac's detail with its building jobs, last jobs and affinity.
- `macs-slots` changes the slots after a confirmation whose button reads `Change to <n>`. "Keep it" changes nothing. A number outside 1 to 99 shows `Slots must be a number from 1 to 99.`, and the current number shows `It already has <n> slots.`
- `macs-disable` disables a Mac after a confirmation that names `cider-build remove <mac>`. The slots field locks with "enable it first" and Enable replaces Disable.
- `macs-enable` enables it again with its previous slots, or 1 per 24 GB of RAM if it had none.
- `macs-unknown`: the drawer for a label the hub doesn't list says `The hub doesn't list this Mac: it is disabled with no heartbeat, or it doesn't exist.`
- `macs-update` offers "Update agent" in the drawer, or says `agent too old to update from here: run cider-build add <mac> once`. See `updates.md`.
- `macs-cli` shows the same states in `cider-build status`.

## How to get to it (user POV)

- Sidebar, then Macs, then click a card (`#maclist a.card`).
- Overview, then the Fleet table (`#ov-fleet`), then click a row or the Mac link.
- Any Mac link in a table or drawer (`#mac/<label>`).
- `CIDER_BUILD_HUB=<url> bin/cider-build status` in a terminal.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has six machines: mac-alpha, mac-beta, mac-epsilon, mac-gamma, mac-zeta and linux-delta. mac-beta is online with 1 slot and 1 build.

The proven journeys are `journeys/macs.mjs` (cards, drawer, validation, slots, disable, enable; it changes mac-beta, so give it its own run) and `journeys/linux.mjs` (the Builds row, the Linux card and drawer).

- **Cards.** Run `t.nav("/#/macs")`. `#maclist .card` has 6 cards. The badge text of mac-epsilon reads `missing tools`, mac-gamma `no heartbeat`, mac-zeta `disabled` and linux-delta `online`. linux-delta's Builds row reads `Android (Linux)` with no Xcode row and `Ubuntu 24.04.3 LTS` in its details; mac-alpha's reads `iOS, Android`; mac-epsilon's reads `nothing yet`.
- **Open drawer.** Run `t.click('#maclist a.card[href="#mac/mac-beta"]')`. `#drawer-title` reads `Mac mac-beta` and the hash is `#/macs/mac/mac-beta`.
- **Validation.** Type `0` and click Change slots: an error toast `Slots must be a number from 1 to 99.` Type `1`: a toast `It already has 1 slots.`
- **Disabled Mac.** Run `t.ev('location.hash = "#mac/mac-zeta"')`. The slots input is disabled, the drawer says `enable it first`, and its agent hint says `run cider-build add mac-zeta once`.
- **Refuse a change.** Run `t.type("#drawer-body input[type=number]", "3")`, `t.click("#drawer-body button", "Change slots")` and `t.click("#confirm-no")`. The confirmation button reads `Change to 3`. `#confirm` closes, and `/api/state` still has slots 1 for mac-beta.
- **Change slots.** Repeat, then run `t.click("#confirm-yes")`. A toast reads `Slots on mac-beta: mac-beta 3`, and `/api/state` has slots 3.
- **Disable.** Run `t.click("#drawer-body button", "Disable")`. The dialog says `run cider-build remove mac-beta from a client`. Run `t.click("#confirm-yes")`. A toast reads `Disable mac-beta: running 1`. After the next poll the drawer badge reads `disabled` and the slots input is disabled.
- **Enable.** Run `t.click("#drawer-body button", "Enable")`, then `t.click("#confirm-yes")`. A toast reads `Enable mac-beta: mac-beta 3` and the badge returns to `online`.
- **Restore.** Set the slots back to 1 with the same steps.
- **CLI.** Run `CIDER_BUILD_HUB=<run url without the trailing slash> bin/cider-build status`. The table lists the same six machines and states, with the header `MAC STATE SLOTS FREE RAM BUILDS XCODE`. linux-delta shows BUILDS `android` and XCODE `-`, mac-alpha `ios,android`, mac-epsilon `-`. The details block shows `Ubuntu 24.04.3 LTS` for linux-delta.
- **Proof.** Take `t.shot` of the confirm dialog and of the drawer after each action. Read `/api/state` for the slots and the enabled flag.

## Gotchas

- Toasts disappear after 5 s, or 9 s for errors. Assert right after the action, or with `t.waitFor`.
- The drawer re-renders its action row only when enabled, slots, used or the agent update state change. Wait for the next 2 s poll before asserting the badge.
- Disabling a Mac with running builds lets them finish, so `used` stays above 0 for a while.
- `mac-zeta` sends heartbeats while disabled. Enabling it makes it take a queued iOS job with source, if one is queued, which changes the queue for later journeys.
- Android stays off the Macs while linux-delta is in the pool, so giving a Mac more slots does not pull the queued Android jobs onto it. Changing linux-delta's slots does, and it changes the seed.
- Never run these actions through `up --real`. The proxy refuses them, so a test there proves nothing and would only show an error toast.
