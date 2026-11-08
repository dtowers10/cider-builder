# Running jobs, queue, live log and cancel

Running & queue lists what each machine is building, with time running, and the queue with each job's position and how long it has waited. A job opens its drawer with every field and its log. The log streams live while the job is active. From the drawer the user can cancel an active job, for every client waiting on it, after a confirmation. Overview repeats the running table under "Building now".

## Sub-features

- `builds-running` lists building jobs with Mac, state and a live timer.
- `builds-queue` lists queued jobs by position, and marks a job with no source yet.
- `builds-drawer` shows a job's fields, cfg and a Download link once it is done.
- `builds-log` streams the log live and strips ANSI codes. It shows "Jump to the end" once the user scrolls up, "Load from the start" when the log is over 1 MiB, and trims the start past 4 MB with a notice.
- `builds-cancel` cancels a queued or building job after a confirmation and updates the queue.
- `builds-overview` repeats the running table and the queued count on Overview.
- `builds-counts` shows building and queued counts on the sidebar Running & queue entry and in the header. `cider-build status` prints the same running table and `Queued: N`, a second way to read the state.

## How to get to it (user POV)

- Sidebar, then Running & queue, then click a row or the job id.
- Overview, then Building now, then click a row. The "N queued" link goes to Running & queue.
- Macs, then a Mac, then Building here or Last 20 jobs, then a row.
- Overview, then Recent failures, then a row. History, then a row.
- Any job link, `#job/<id>`.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. Four jobs are building: `demo ios` and `shop android` on mac-alpha, `ledger ios` on mac-beta, `scanner android` on linux-delta. Three are queued: `scanner android` and `demo android` with source, held for linux-delta, and `shop ios` with no source.

The proven journey is `journeys/builds.mjs`. It cancels the queued `demo android`, so give it its own run. `journeys/warm.mjs` covers warmed jobs in the queue and drawer.

- **Running.** Run `t.nav("/#/builds")`. `#running tbody tr` has 4 rows, including `scanner android` on `linux-delta`, and their time cells change from one second to the next. `#nav a[href="#/builds"] .nav-count` reads `4 building3 queued`.
- **Queue.** `#queue tbody tr` has the positions 1, 2, 3: `scanner android`, `demo android`, then `shop ios` with the badge `no source yet`.
- **Live log.** Run `t.click('#running a[href^="#job/"]')`. The drawer title starts with `Job `, `.log-status` reads `Live: updates every second.`, and `pre.log` gains a `CompileSwift … Module<n>.swift` line every 2 s, with no escape codes in its text.
- **Cancel, refuse.** Open the queued `demo android` from `#queue` (it has source; the no-source job is replaced by the fleet), then run `t.click("#drawer-body button.danger")`. The `#confirm` title is `Cancel job <id>`, its body says `It leaves the queue and never reaches a Mac.`, and focus is on `#confirm-no`. Run `t.click("#confirm-no")`. The job is still in `/api/state`.
- **Cancel.** Repeat, then run `t.click("#confirm-yes")`. A toast reads `Cancel <id>: cancelled`, the drawer badge reads `cancelled`, the queue loses that row, the positions renumber 1, 2, and the sidebar's queued count drops by one.
- **Done job.** Open a `done` job from History. The drawer has `Download <key>-<plat>.<ext>`, and `.log-status` reads `Log complete (<size>).` On the seed the file is usually not in the cache, so assert on the link text, don't download it.
- **Overview.** Run `t.nav("/#/overview")`. `#ov-running tbody tr` has the same jobs as `#running`. `#ov-queued a` reads `<n> queued` and links to `#/builds`.
- **Proof.** Take a screenshot of the drawer with the streaming log and of the confirm dialog. Read `/api/state` before and after the cancel.

## Gotchas

- Cancelling a building iOS job on a Mac frees a slot, but nothing starts there: the queued Android jobs only go to linux-delta while it is in the pool, and the queued `shop ios` has no source. Cancelling linux-delta's `scanner android` does free a usable slot. The hub then assigns the oldest queued Android job, and the counts change in two steps.
- The seeded `shop android` on mac-alpha predates the Linux-only rule. New Android jobs never land on a Mac while linux-delta is in the pool.
- The queued job with no source is replaced every 120 s with a new id. Pick jobs from the table at run time.
- The log reads the last 1 MiB first. Seeded logs are small, so "Load from the start" does not show on the seed.
- The fleet stops logging a job as soon as the hub answers 409 for it, which happens after a cancel.
