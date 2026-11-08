# History search and filters

History lists finished jobs (done, failed and cancelled), newest first, with finished time (a link), project, platform, client, Mac, duration, rc and state. The user narrows it with a free-text search and filters by state, platform, Mac and client. A count reads "<shown> of <total>". The filters survive the panel's automatic refresh. Overview links to History filtered to failures.

## Sub-features

- `history-list` shows finished jobs newest first, each row opening the job drawer.
- `history-search` matches id, project, key, client or Mac, without regard to case.
- `history-filters` filters by state, platform, Mac and client. State has fixed options. Platform, Mac and Client options come from the jobs (in the seed, Mac lists mac-alpha, mac-beta and mac-gamma).
- `history-count` reads `<shown> of <total>`, plus `(showing 500)` past 500 rows.
- `history-persist` keeps the query and filters when new history arrives.
- `history-failures-link` opens History filtered to `failed` from Overview's "All failures in History".

## How to get to it (user POV)

- Sidebar, then History.
- Overview, then Recent failures, then "All failures in History".
- `#/history`, or the old `#historial`.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has 42 finished jobs, 11 of them `ledger` jobs (9 `done`), and 6 `failed` jobs, 2 of them in the last 24 h. About every 2 min the fleet's no-source `shop ios` expires and adds one cancelled job (client `elena`, no Mac), so read the total from `/api/history` instead of hard-coding it.

The proven journey is `journeys/history.mjs` (read-only).

- **List.** Run `t.nav("/#/history")`. `#f-count` reads `<total> of <total>`, where the total is `/api/history`'s job count (42 in the first 2 min).
- **Search.** Run `t.type("#f-q", "ledger")`. Every row's Project cell is `ledger`.
- **Filter.** Run `t.select("#f-state", "done")`. `#f-count` reads `9 of <total>` and every State badge reads `done`.
- **Survives refresh.** Cancel a queued job through the hub, so that new history arrives. Use the UI in `builds.md`, or for setup only `t.ev('fetch("/detach?job=<id>&all=1", {method: "POST"})')`. Within 4 s `#f-count` total goes up by at least one (a no-source expiry may land in the same window), while `#f-q` still holds `ledger`, `#f-state` still holds `done`, and the view is still History.
- **Open a row.** Run `t.click("#histlist tbody tr td:nth-child(2)")`. The drawer opens with the hash `#/history/job/<id>`. `t.back()` closes it and the filters are unchanged.
- **Failures link.** Run `t.nav("/#/overview")`. `#ov-failures tbody tr` has 2 rows, the seeded failures from the last 24 h. Run `t.click("#ov-all-failures")`. The view is History, `#f-state` is `failed`, and `#f-count` reads `6 of <total>`.
- **Proof.** Take a screenshot of the filtered list with the drawer over it, plus the journal lines with the count before and after the refresh.

## Gotchas

- Filters are not in the URL. A cold `t.nav` resets them. That is by design.
- The option lists of `#f-plat`, `#f-mac` and `#f-client` are rebuilt only when the set of values changes. A selected value that disappears stays selectable.
- History refreshes only when `history_rev` changes, that is when a job finishes. On a seeded run that also happens about every 2 min, when the fleet's no-source job expires (`SOURCE_TTL`).
- Overview's "All failures in History" sets only `#f-state=failed`. A search or another filter set earlier in the same page stays. Start from a cold load to see `6 of <total>`.
- `t.select` moves with arrow keys on a closed native select. The option must exist in the list, or the helper throws.
