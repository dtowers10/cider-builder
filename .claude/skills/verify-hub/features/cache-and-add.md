# Cache, affinity and Add a Mac

Cache & affinity lists every cached artifact by project, with size, date and a Download link, and the project-to-Mac affinity that each successful build records. Add a Mac shows the commands to join a new Mac, built from the hub's own tailnet IP, name and port, each with a Copy button, plus the client commands to add and remove a Mac.

## Sub-features

- `cache-list` shows each project with its total size and its files, newest first.
- `cache-download` serves an artifact from `/cache/<project>/<file>` as a download.
- `cache-invalidate`: each artifact row has an `Invalidate` button that, after confirmation, sends `DELETE /cache/<project>/<file>` and reloads the list. An unknown file answers 404 and a name starting with `.` answers 400.
- `cache-delete-project`: each project head has a `Delete all` button that, after confirmation, sends `DELETE /cache/<project>`, which deletes the project's artifacts but keeps its directory. A project with no artifacts left drops out of the list.
- `cache-affinity` lists project, platform and Mac, with Mac links.
- `cache-eviction`: the hub keeps the `CIDER_BUILD_CACHE_KEEP` (default 5) most recently used artifacts per project and platform, pruning every `CIDER_BUILD_CACHE_PRUNE_S` (default 600) s. `journeys/cache-eviction.mjs` checks the list after a prune; start the run with small values of both, e.g. `CIDER_BUILD_CACHE_KEEP=3 CIDER_BUILD_CACHE_PRUNE_S=30 hubctl.py up`.
- `add-commands` shows `curl -fsSL http://<ip>:<tailnet port>/join | bash`, the short-name variant with `--slots 2`, and `cider-build add` and `cider-build remove`.
- `add-copy` copies a command and shows the toast `Copied.`.
- `add-join` serves the `/join` script that the first command downloads.
- `add-refused` names, from `/api/state`, the Macs the hub refuses: the hub itself by its tailnet name, and the Macs in its `exclude` setting.

## How to get to it (user POV)

- Sidebar, then Cache & affinity, or `#/cache`, or the old `#cache`.
- Sidebar, then Add a Mac, or `#/add`, or the old `#unir`.
- A done job's drawer, then `Download <key>-<plat>.<ext>`, for a single artifact.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has the 4 projects demo, ledger, scanner and shop, with 2 artifacts each and one affinity row each.

- **Cache list.** Run `t.nav("/#/cache")`. `#cachelist .proj` has 4 blocks and each one has 2 rows.
- **Download.** Read the first `#cachelist a[download]` href with `t.ev`, then fetch it with `t.ev(fetch(href).then(r => [r.status, r.headers.get("content-type")]))`. The answer is `200` and `application/octet-stream`. A click starts a download that headless Chrome does not save, so assert on the link and the response.
- **Invalidate.** Run `t.click("#cachelist button", "Invalidate")`, then `t.click("#confirm-yes")`. A toast reads `Invalidate <file>: deleted <project>/<file>` and that project has 1 row.
- **Delete all.** Run `t.click("#cachelist .proj-head button", "Delete all")`, then `t.click("#confirm-yes")`. A toast reads `Delete cache of <project>: deleted <n> artifacts of <project>` and `#cachelist .proj` has one block less. These two change the seeded cache, so run them last or on a fresh run. `journeys/cache-delete.mjs` drives both.
- **Affinity.** `#afflist tbody tr` has 4 rows. Run `t.click('#afflist a[href^="#mac/"]')`, which opens that Mac's drawer over Cache.
- **Commands.** Run `t.nav("/#/add")`. The `#join code` texts are `curl -fsSL http://127.0.0.1:<tailnet port>/join | bash`, `curl -fsSL http://verify-hub-<id>:<tailnet port>/join | bash -s -- --slots 2`, `cider-build add <mac> [slots]` and `cider-build remove <mac>`.
- **Refused.** On the same view, the last `#join p.note` ends with `The hub itself (verify-hub-<id>) refuses to join.` On a run started with `CIDER_BUILD_EXCLUDE=my-laptop hubctl.py up` it ends with `The hub itself (verify-hub-<id>) and my-laptop, in the hub's exclude setting, refuse to join.`
- **Copy.** Run `t.click("#join .cmd button", "Copy")`. A toast reads `Copied.`, or `Selected: copy it with Ctrl+C (⌘C on a Mac).` when the clipboard is unavailable.
- **Join script.** Run `curl -fsS http://127.0.0.1:<tailnet port>/join | head -4` in a terminal. Its first three lines include `#!/usr/bin/env bash` and `export CIDER_BUILD_HUB=https://verify-hub-<id>.example.ts.net:<port>`.
- **Proof.** Take screenshots of both views and save the `/join` head in the journal or a file in the evidence dir.

## Gotchas

- The tailnet port of a seeded run is in `/tmp/verify-hub/run-<id>/state.json` (`tailnet_port`), not in the URL.
- Never pipe the `/join` script into `bash` on this machine. It installs a builder agent. Read it only.
- In headless Chrome the clipboard API may be refused. Then the panel falls back to selecting the text, and both toasts are correct behaviour. Assert that one of them appears.
- On the real hub (`up --real`) the commands show the real tailnet IP and name, which is a read-only check that is worth doing after a hub change.
