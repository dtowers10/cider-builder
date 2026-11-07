# Board: slots, estimates, queue forecast, last 24 h, job detail, live log and cancel

The Board is the home view. It has one row per Mac and one cell per slot. A cell shows the build running there (project, platform, client), a 2 px meter, its elapsed time and the estimated time left, or `running long` once past the estimate. Free slots say `free`. A Mac that takes no builds shows why in its row with the direct action (`Enable`) or a `Why` link to its drawer. On the right, the queue lists each job's position, waiting time and a forecast of when and on which Mac it starts, and `Last 24 h` lists the done and failed jobs with a link to History. A job opens a wide drawer: one header line, a `Details` disclosure with every field, a log toolbar and the log at full height. The log streams live while the job is active. From the drawer the user can cancel an active job, for every client waiting on it, after a confirmation.

## Sub-features

- `board-lanes` shows one `.lane` per Mac with `max(slots, used)` cells: `.cell.job` for a build, `.cell.ghost` for a cancelled run the agent still reports, `.cell.free` for an open slot, and one `.cell.off` for a Mac that takes no builds, with the reason and `Enable` (disabled Mac) or `Why` (anything else). The heading reads `Macs · <busy> of <slots> slots busy`.
- `board-eta` estimates each build's end from the median duration of earlier `done` builds of the same project and platform (at least 2 samples). The cell shows `~<m>m<s>s left` and a meter, or `running long` in yellow once past it. With fewer than 2 samples it shows the elapsed time only. An `assigned` job (handed to a Mac, not yet building) reads `assigned · starting`.
- `board-forecast` mirrors the hub's scheduler for the queue: jobs with source in `created` order, the affinity Mac when it has a free slot, else the Mac with the most free RAM, and a slot frees when its build reaches its typical time. Each item reads `starts in ~<time> on <mac>` or `starts soon on <mac>` when a slot is overdue. A job with no source reads `no source yet · cancelled in ~<time> if none`. The list is labelled `Start times are estimates from typical build times.`
- `board-recent` lists the done and failed jobs of the last 24 h, newest first (at most 10), under `Last 24 h · <n> failed`, with `All history` and `Failures in History` links.
- `board-detail` opens a job in `#drawer.wide` with `.job-head` (project, platform, state badge, elapsed or duration, `typical <time>`, time left or `running long`, client, `on <mac>`, kind, `<n> clients waiting`, `Details`, `Cancel job` or `Download <key>-<plat>.<ext>`). `Details` unfolds `#job-more`, the full key/value list.
- `board-log` streams the log live into `pre.log`, strips ANSI codes, and has a toolbar: `Search the log` with a `.log-find` count (`<n> hits`, then `<i> of <n>` as Enter and Shift+Enter move through them), `Wrap`, `From start` (enabled when the tail was cut at 1 MiB) and `Follow` (scrolling up turns it off), plus `.log-status`.
- `board-cancel` cancels a queued or building job after a confirmation and updates the queue and the counts.

## How to get to it (user POV)

- The top bar's Board entry, `#/board`, an empty hash, or the old `#/overview`, `#/builds` and `#trabajos`.
- A cell, a queue item or a `Last 24 h` item (the whole box is clickable), or any job link, `#job/<id>`.
- `Why` in an off cell opens the Mac's drawer; `Enable` asks to enable it.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. Three jobs are building and three are queued (one with no source). History gives 3m00s typical builds for every project except `shop android`, which has one done sample.

The proven journey is `journeys/board.mjs`. It ends in a cancel, so run it after the read-only journeys.

- **Lanes.** Run `t.nav("/#/board")`. `#board-lanes .lane` has 5 lanes and the `h3` reads `Macs · 3 of 6 slots busy`. `.lane[data-id="mac-alpha"] .cell.job` has 2 cells: `demo ios ci-runner …` includes `running long` (it started 290 s before the seed, past 3m00s) and `shop android daniel …` shows the elapsed time only. mac-beta's `ledger ios elena` cell reads `~<m>m<s>s left` with a `.meter span[data-fill]`, or `running long` about 2 min after `up`. `.cell.off` texts are `missing tools · Why`, `no heartbeat · lost 1 h ago · Why` and `disabled · Enable`. A `[data-since]` text changes from one second to the next.
- **Queue.** `#board-queue li` has 3 items: `1 · scanner android ci-runner … starts soon on mac-alpha` (alpha is its affinity Mac and its demo slot is overdue), `2 · demo android daniel … starts in ~… on mac-beta` (or `soon` once ledger is overdue), and `3 · shop ios elena …` with the `.b-nosrc` badge and `cancelled in ~… if none`.
- **Last 24 h.** `#board-recent h3` reads `Last 24 h · 2 failed`, `#board-recent li` has 9 items and 2 of them hold `.b-failed`.
- **Why and Enable.** Run `t.click("#board-lanes .cell.off a", "Why")`: `#drawer-title` reads `Mac mac-epsilon` and the first `#drawer-body p.note` names `xcodegen, Java 17`. Run `t.click("#board-lanes .cell.off button", "Enable")`: `#confirm-title` reads `Enable mac-zeta` with focus on `#confirm-no`. `t.click("#confirm-no")` leaves it disabled in `/api/state`.
- **Job detail and log.** Run `t.click('#board-lanes .lane[data-id="mac-alpha"] .cell.job a[href^="#job/"]')`. `.job-head` reads `demo ios building <elapsed> typical 3m00s running long ci-runner on mac-alpha expo <n> clients waiting Details Cancel job`, `pre.log` reaches near the bottom of the window, `.log-status` starts with `Live: updates every second.` and `pre.log` gains a `CompileSwift … Module<n>.swift` line every 2 s with no escape codes. `#job-more` is hidden and `Details` has `aria-expanded="false"`; `t.click("#drawer-body button", "Details")` shows it with `Source uploaded yes` and `cfg.MB_SCHEME`.
- **Search, Wrap, Follow.** Run `t.type(".log-tools input[type=search]", "Module")`: `.log-find` reads `<n> hits`. `t.press("Enter")` makes it `1 of <n>` and `Follow` gets `aria-pressed="false"`. `t.click(".log-tools button", "Follow")` turns it back on. `t.click(".log-tools button", "Wrap")` adds `nowrap` to `pre.log`. `From start` is disabled, because the seeded log is shown from byte 0.
- **Narrow.** Run `t.size(390, 800)` and `t.nav("/#/board")`: the lanes stack (one column), free cells are hidden, and `scrollWidth` is at most 390.
- **Cancel, refuse.** At 1280x800 on `#/board`, read the id of `#board-queue li:nth-child(2)` from its `data-id`, click its `a[href^="#job/"]`, then run `t.click("#drawer-body button.danger")`. `#confirm-title` reads `Cancel job <id>` and focus is on `#confirm-no`. `t.click("#confirm-no")` leaves the job queued in `/api/state`.
- **Cancel.** Repeat, then `t.click("#confirm-yes")`. A toast reads `Cancel <id>: cancelled`, the `.job-head .badge` reads `cancelled`, `#board-queue li` drops to 2 and the Board count reads `3 building2 queued`.
- **Done job.** Open a `done` job from History (see `history.md`). `.job-head` has `Download <key>-<plat>.<ext>` and `.log-status` reads `Log complete (<size>).`
- **Proof.** The journey writes `board.png`, `job-detail.png`, `board-narrow.png`, `cancel-confirm.png` and `cancel-after.png`, and reads `/api/state` before and after the cancel.

## Gotchas

- The elapsed times and the `left` and `in ~` countdowns tick every second through `data-*` attributes; nothing re-renders for them. Compare two reads a second apart, do not assert an exact value.
- Estimates come from `/api/history` and are recomputed only when a job finishes. On the seed every typical duration is 3m00s.
- Cancelling a building job frees a slot, so the hub assigns the next queued job and the fleet starts building it. The counts change in two steps. Cancelling a queued job (as the journey does) changes only the queue.
- The queued job with no source is replaced every 120 s with a new id. Pick jobs from the page at run time, through `data-id`.
- The log reads the last 1 MiB first. Seeded logs are small, so `From start` is disabled on the seed.
- The fleet stops logging a job as soon as the hub answers 409 for it, which happens after a cancel.
- A search hit split across two log chunks is not counted. The count caps at 1000 hits (`1000+`).
- Log hits are highlighted with the CSS Custom Highlight API. Headless Chrome has it; without it, the count and the scroll still work.
