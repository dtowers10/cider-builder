# Hub panel verification map

This directory is the maintained source for verifying what users of the cider-build hub see and do in its web panel, plus the `cider-build status` CLI. Read this index before driving, then use the matching feature file as the recipe. A proof that drives one convenient entry point is incomplete when a file lists others.

## Baseline preconditions

- A seeded run started with `python3 .claude/skills/verify-hub/scripts/hubctl.py up`, with `VERIFY_HUB_RUN` exported.
- `hubctl.py doctor` exits 0 for that run.
- The seeded state described in `../SKILL.md` (Launch), not changed by an earlier mutation journey in the same run.
- Viewport 1280x800, which `drive.mjs` sets at the start, unless the recipe says 390x800.
- Never drive an instance this run did not start. Use the real hub only through `hubctl.py up --real`, and only read it.

## Driving conventions

- Run every recipe as a journey file through `node .claude/skills/verify-hub/scripts/drive.mjs <journey.mjs>`. Keep journeys next to `../journeys/navigation.mjs`.
- `t.nav(url)` is a cold load. Clicks and `location.hash` changes are in-app navigation. They behave differently on purpose (see `navigation.md`).
- Act with `t.click`, `t.press`, `t.type` and `t.select`. Read with `t.ev` and `t.waitFor`.
- Buttons have no ids. Pick them by visible text with `t.click(scope, "Text")`.
- Every action that changes the hub asks for confirmation first. Confirm with `#confirm-yes`, refuse with `#confirm-no`.
- Lanes, cards and list items carry `data-id` (the Mac label or the job id), so `#maclist .card[data-id="mac-beta"]` and `#board-queue li[data-id="<job>"]` pick one of them.

## Proof and skip reporting

- Quote the journal's `RESULT` line and every `FAIL` line.
- UI proof includes a screenshot that shows the top bar or the drawer title, so the view is identifiable.
- Mutation proof reads the stored value a second way: `/api/state` through `t.ev(fetch(...))`, or `bin/cider-build status`.
- Record the feature ID and the entry point with every artifact.
- If a precondition is missing from the seed, report the journey as failed and name the precondition. Do not weaken the journey.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behaviour. It then has exactly four H2 sections, in this order:

1. `Sub-features` lists short IDs, with one line for each behaviour.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with drive.mjs` starts with `Preconditions:`, then pairs each user action with exact journey calls and the observable result.
4. `Gotchas` lists traps that can waste or invalidate a run.

## Features

| Feature | File | Proven journey |
|---|---|---|
| Top bar navigation, routes, alerts and counts | [navigation.md](./navigation.md) | `journeys/navigation.mjs` |
| Board: slots, estimates, queue forecast, last 24 h, job detail, live log and cancel | [board.md](./board.md) | `journeys/board.mjs`; `journeys/warm.mjs` (warmed jobs on the Board and in the drawer only; run `cider-build warm` in a folder named `warmproj` first) |
| Fleet: the Mac cards and their actions | [fleet.md](./fleet.md) | `journeys/fleet.mjs` |
| History search, window chips and filters | [history.md](./history.md) | `journeys/history.mjs` |
| Cache, affinity and Add a Mac | [cache-and-add.md](./cache-and-add.md) | `journeys/cache-delete.mjs`; `journeys/cache-eviction.mjs` on a run started with small `CIDER_BUILD_CACHE_KEEP` and `CIDER_BUILD_CACHE_PRUNE_S` |
| Updates: the hub from its git repository, the agents from the hub | [updates.md](./updates.md) | `journeys/updates.mjs`; `journeys/updates-off.mjs` on a run started with `up --no-updates` |

Run the read-only journeys first (`navigation`, `history`), then the ones that change the seed (`board` cancels a queued job, `fleet` changes mac-beta and restores it, `cache-delete`, `updates`), or give each of those its own run.

When you prove a feature, add its journey to `../journeys/` and to this table.
