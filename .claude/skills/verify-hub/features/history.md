# History search, window chips and filters

History lists finished jobs (done, failed and cancelled), newest first, with project, platform, client, Mac, duration, rc and state. The user narrows it with a free-text search, the window chips `24 h` and `All`, a `Failed` chip, and filters by state, platform, Mac and client. A count reads "<shown> of <total>". The filters survive the panel's automatic refresh. The Board links to History filtered to failures.

## Sub-features

- `history-list` shows finished jobs newest first, each row opening the job drawer. Below 860 px the rows read as labelled cards.
- `history-search` matches id, project, key, client or Mac, without regard to case.
- `history-window` keeps jobs finished in the last `24 h` or `All` of them. The hub keeps 7 days, so `All` is the whole week.
- `history-filters` filters by state, platform, Mac and client. The option lists come from the data. The `Failed` chip mirrors the state select.
- `history-count` reads `<shown> of <total>`, plus `(showing 500)` past 500 rows.
- `history-persist` keeps the query and filters when new history arrives.
- `history-failures-link` opens History filtered to `failed` from the Board's `Failures in History` link.

## How to get to it (user POV)

- The top bar's History entry, `#/history`, or the old `#historial`.
- The Board's `All history` and `Failures in History` links under `Last 24 h`.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has 42 finished jobs at `up` (plus one cancelled job every 120 s, the job with no source), 33 of them `done`, 9 of those `ledger`, and 6 `failed`, 2 of them in the last 24 h.

The proven journey is `journeys/history.mjs`. It reads the expected counts from `/api/history` at run time, because the total grows. It cancels the queued job with no source to make new history arrive; the fleet replaces that job at once.

- **List.** Run `t.nav("/#/history")`. `#f-count` reads `<total> of <total>` and `#histlist thead` is displayed.
- **Window.** Run `t.click("#f-when label", "24 h")`: the count is the number of jobs finished in the last 24 h. `t.click(".filters label", "Failed")` sets `#f-state` to `failed` and the count to `2 of <total>`. `t.click("#f-when label", "All")` gives `6 of <total>`.
- **Filter.** Run `t.select("#f-state", "done")`: `#f-failed` is unticked, the count reads `33 of <total>` and every State badge reads `done`. `t.select("#f-mac", "mac-beta")` leaves only rows whose Mac cell is `mac-beta`; `t.select("#f-mac", "")` clears it.
- **Search.** Run `t.type("#f-q", "ledger")`. The count reads `9 of <total>` and every Project cell is `ledger`.
- **Survives refresh.** Cancel the queued job with no source, for setup only: `t.ev('fetch("/detach?job=<id>&all=1", {method: "POST"})')`. Within 8 s the total goes up by one, while `#f-q` still holds `ledger`, `#f-state` still holds `done`, and the view is still History.
- **Open a row.** Run `t.click("#histlist tbody tr td:nth-child(2)")`. The drawer opens with the hash `#/history/job/<id>`, `.job-head` has `Download k…` and `.log-status` reads `Log complete (…)`. `t.back()` closes it and the filters are unchanged.
- **Failures link.** Run `t.nav("/#/board")`. `#board-recent li .b-failed` has 2 items. Run `t.click("#board-failures")`. The view is History, `#f-failed` is ticked, `#f-state` is `failed`, and `#f-count` reads `6 of <total>`.
- **Proof.** The journey writes `history-filtered.png`, `history-drawer.png` and `history-failures.png`, and the journal holds the count before and after the refresh.

## Gotchas

- Filters are not in the URL. A cold `t.nav` resets them to `All` and no filter. That is by design.
- The option lists of `#f-plat`, `#f-mac` and `#f-client` are rebuilt only when the set of values changes. A selected value that disappears stays selectable.
- History refreshes only when `history_rev` changes, that is when a job finishes. Waiting does not trigger a refresh by itself, but the hub cancels the job with no source every 120 s, so the total grows by one each time.
- `t.select` moves with arrow keys on a closed native select. The option must exist in the list, or the helper throws.
- `t.type` replaces the field's content; to clear `#f-q`, type a query that matches everything, or reload.
