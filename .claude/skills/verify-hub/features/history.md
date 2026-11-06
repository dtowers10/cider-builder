# History search and filters

History lists finished jobs (done, failed and cancelled), newest first, with project, platform, client, Mac, duration, rc and state. The user narrows it with a free-text search and filters by state, platform, Mac and client. A count reads "<shown> of <total>". The filters survive the panel's automatic refresh. Overview links to History filtered to failures.

## Sub-features

- `history-list` shows finished jobs newest first, each row opening the job drawer.
- `history-search` matches id, project, key, client or Mac, without regard to case.
- `history-filters` filters by state, platform, Mac and client. The option lists come from the data.
- `history-count` reads `<shown> of <total>`, plus `(showing 500)` past 500 rows.
- `history-persist` keeps the query and filters when new history arrives.
- `history-failures-link` opens History filtered to `failed` from Overview's "All failures in History".

## How to get to it (user POV)

- Sidebar, then History.
- Overview, then Recent failures, then "All failures in History".
- `#/history`, or the old `#historial`.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has 42 finished jobs, 9 of them `ledger` jobs in state `done`, and 6 `failed` jobs, 2 of them in the last 24 h.

- **List.** Run `t.nav("/#/history")`. `#f-count` reads `42 of 42`, or more if the run has cancelled jobs.
- **Search.** Run `t.type("#f-q", "ledger")`. Every row's Project cell is `ledger`.
- **Filter.** Run `t.select("#f-state", "done")`. `#f-count` reads `9 of <total>` and every State badge reads `done`.
- **Survives refresh.** Cancel a queued job through the hub, so that new history arrives. Use the UI in `builds.md`, or for setup only `t.ev('fetch("/detach?job=<id>&all=1", {method: "POST"})')`. Within 4 s `#f-count` total goes up by one, while `#f-q` still holds `ledger`, `#f-state` still holds `done`, and the view is still History.
- **Open a row.** Run `t.click("#histlist tbody tr td:nth-child(2)")`. The drawer opens with the hash `#/history/job/<id>`. `t.back()` closes it and the filters are unchanged.
- **Failures link.** Run `t.nav("/#/overview")`. `#ov-failures tbody tr` has 2 rows, the seeded failures from the last 24 h. Run `t.click("#ov-all-failures")`. The view is History, `#f-state` is `failed`, and `#f-count` reads `6 of <total>`.
- **Proof.** Take a screenshot of the filtered list with the drawer over it, plus the journal lines with the count before and after the refresh.

## Gotchas

- Filters are not in the URL. A cold `t.nav` resets them. That is by design.
- The option lists of `#f-plat`, `#f-mac` and `#f-client` are rebuilt only when the set of values changes. A selected value that disappears stays selectable.
- History refreshes only when `history_rev` changes, that is when a job finishes. Waiting does not trigger a refresh by itself.
- `t.select` moves with arrow keys on a closed native select. The option must exist in the list, or the helper throws.
