# Running jobs, queue, live log and cancel

Running & queue lists what each Mac is building, with time running, and the queue with each job's position and how long it has waited. A job opens its drawer with every field and its log. The log streams live while the job is active. From the drawer the user can cancel an active job, for every client waiting on it, after a confirmation. Overview repeats the running table under "Building now".

## Sub-features

- `builds-running` lists building jobs with Mac, state and a live timer.
- `builds-queue` lists queued jobs by position, and marks a job with no source yet.
- `builds-drawer` shows a job's fields, cfg and a Download link once it is done.
- `builds-log` streams the log live, strips ANSI codes, and offers "Load from the start" and "Jump to the end".
- `builds-cancel` cancels a queued or building job after a confirmation and updates the queue.
- `builds-overview` repeats the running table and the queued count on Overview.

## How to get to it (user POV)

- Sidebar, then Running & queue, then click a row or the job id.
- Overview, then Building now, then click a row. The "N queued" link goes to Running & queue.
- Any job link, `#job/<id>`.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. Three jobs are building and at least two are queued.

- **Running.** Run `t.nav("/#/builds")`. `#running tbody tr` has 3 rows, and their time cells change from one second to the next.
- **Queue.** `#queue tbody tr` has the positions 1, 2, 3. The job with no source shows the badge `no source yet`.
- **Live log.** Run `t.click('#running a[href^="#job/"]')`. The drawer title starts with `Job `, `.log-status` reads `Live: updates every second.`, and `pre.log` gains a `CompileSwift … Module<n>.swift` line every 2 s, with no escape codes in its text.
- **Cancel, refuse.** Open a queued job from `#queue`, then run `t.click("#drawer-body button.danger")`. The `#confirm` title is `Cancel job <id>` and focus is on `#confirm-no`. Run `t.click("#confirm-no")`. The job is still in `/api/state`.
- **Cancel.** Repeat, then run `t.click("#confirm-yes")`. A toast reads `Cancel <id>: cancelled`, the drawer badge reads `cancelled`, the queue loses that row and the sidebar's queued count drops by one.
- **Done job.** Open a `done` job from History. The drawer has `Download <key>-<plat>.<ext>`, and `.log-status` reads `Log complete (<size>).`
- **Overview.** Run `t.nav("/#/overview")`. `#ov-running tbody tr` has the same jobs as `#running`. `#ov-queued a` reads `<n> queued` and links to `#/builds`.
- **Proof.** Take a screenshot of the drawer with the streaming log and of the confirm dialog. Read `/api/state` before and after the cancel.

## Gotchas

- Cancelling a building job frees a slot, so the hub assigns the next queued job and the fleet starts building it. The counts change in two steps.
- The queued job with no source is replaced every 120 s with a new id. Pick jobs from the table at run time.
- The log reads the last 1 MiB first. Seeded logs are small, so "Load from the start" does not show on the seed.
- The fleet stops logging a job as soon as the hub answers 409 for it, which happens after a cancel.
