# Cache, affinity and Add a Mac

Cache & affinity lists every cached artifact in one table grouped by project (a `tbody.proj` each, with `data-proj`), one `tr.file` per artifact with `data-file`, its version, platform, size, last use, a quiet Download link and a quiet Invalidate button (Invalidate, like the project's Clear cache, turns red only on hover or keyboard focus), and the project-to-Mac affinity that each successful build records. Add a Mac shows the commands to join a new Mac or Linux machine, built from the hub's own tailnet IP, name and port, each with a Copy button, plus the client commands to add and remove a Mac, and a note that Linux machines build Android only.

## Sub-features

- `cache-list` shows each project with `<n> versions, <total size>` and its files, newest by use first (a download updates an artifact's last use).
- `cache-download` serves an artifact from `/cache/<project>/<file>` as a download.
- `cache-invalidate`: each artifact row has an `Invalidate` button that, after confirmation, sends `DELETE /cache/<project>/<file>` and reloads the list. An unknown file answers 404 and a name starting with `.` answers 400.
- `cache-delete-project`: each project head has a `Clear cache` button that, after confirmation, sends `DELETE /cache/<project>`, which deletes the project's artifacts but keeps its directory. A project with no artifacts left drops out of the list.
- `cache-affinity` lists project, platform and Mac, with Mac links. It is only a preference among the machines allowed to build that platform, so with a Linux machine in the pool an Android row may still name a Mac. A Mac's drawer shows its own affinity rows.
- `cache-eviction`: the hub keeps the `CIDER_BUILD_CACHE_KEEP` (default 5) most recently used artifacts per project and platform, pruning every `CIDER_BUILD_CACHE_PRUNE_S` (default 600) s. It never deletes an artifact being downloaded or one an active job is about to deliver. `journeys/cache-eviction.mjs` checks the list after a prune; see the Eviction step.
- `add-commands` shows `curl -fsSL http://<ip>:<tailnet port>/join | bash`, the short-name variant with `--slots 2`, and `cider-build add` and `cider-build remove`.
- `add-copy` copies a command and shows the toast `Copied.`.
- `add-join` serves the `/join` script that the first command downloads.
- `add-linux` notes, as the last `#join p.note`, `A Linux machine (x86-64, with apt) builds Android only. While one is in the pool, Android builds go to the Linux machines and the Macs keep to iOS.`
- `add-refused` names, from `/api/state`, the Macs the hub refuses: the hub itself by its tailnet name, and the Macs in its `exclude` setting.

## How to get to it (user POV)

- Sidebar, then Cache & affinity, or `#/cache`, or the old `#cache`.
- Sidebar, then Add a Mac, or `#/add`, or the old `#unir`.
- A done job's drawer, then `Download <key>-<plat>.<ext>`, for a single artifact.

## Driving it with drive.mjs

Preconditions:

- A seeded run that passes `doctor`. It has the 4 projects demo, ledger, scanner and shop, with 2 artifacts each (`k0001` and `k0002`) and one affinity row each.

The proven journeys are `journeys/cache-add.mjs` (list, download, affinity and Add a Mac; read-only), `journeys/cache-delete.mjs` (invalidate and clear; mutates) and `journeys/cache-eviction.mjs` (see the Eviction step).

- **Cache list.** Run `t.nav("/#/cache")`. `#cachelist .proj` has 4 blocks and each one has 2 `tr.file` rows.
- **Download.** Read the first `#cachelist a[download]` href with `t.ev`, then fetch it with `t.ev(fetch(href).then(r => [r.status, r.headers.get("content-type")]))`. The answer is `200` and `application/octet-stream`. A click starts a download that headless Chrome does not save, so assert on the link and the response.
- **Invalidate.** Run `t.click("#cachelist button", "Invalidate")`, then `t.click("#confirm-yes")`. A toast reads `Invalidate <file>: deleted <project>/<file>` and that project has 1 row.
- **Clear cache.** Run `t.click("#cachelist .proj-head button", "Clear cache")`, then `t.click("#confirm-yes")`. A toast reads `Clear cache of <project>: deleted <n> artifact(s) of <project>` (`1 artifact` after the Invalidate step) and `#cachelist .proj` has one block less. These two change the seeded cache, so run them last or on a fresh run. `journeys/cache-delete.mjs` drives both.
- **Affinity.** `#afflist tbody tr` has 4 rows. Run `t.click('#afflist a[href^="#mac/"]')`, which opens that Mac's drawer over Cache.
- **Eviction.** Start a run with `CIDER_BUILD_CACHE_KEEP=3 CIDER_BUILD_CACHE_PRUNE_S=10 hubctl.py up` (the setting's minimum is 5 s). The seed has only 2 artifacts per project, so add `k0003`, `k0004` and `k0005-ios.app.tar.gz` to `/tmp/verify-hub/run-<id>/home/cache/demo/` a second apart and wait past the next prune. `k0001` survives, because the seeded building `demo ios` job has key `k0001`. Run `PRUNED=k0002-ios.app.tar.gz KEPT=k0005-ios.app.tar.gz,k0004-ios.app.tar.gz,k0003-ios.app.tar.gz,k0001-ios.app.tar.gz node .claude/skills/verify-hub/scripts/drive.mjs .claude/skills/verify-hub/journeys/cache-eviction.mjs`, then check with curl that `/cache/demo/k0002-ios.app.tar.gz` answers 404.
- **Commands.** Run `t.nav("/#/add")`. The `#join code` texts are `curl -fsSL http://127.0.0.1:<tailnet port>/join | bash`, `curl -fsSL http://verify-hub-<id>:<tailnet port>/join | bash -s -- --slots 2`, `cider-build add <mac> [slots]` and `cider-build remove <mac>`.
- **Linux note.** The last `#join p.note` is the `add-linux` text.
- **Refused.** On the same view, the second-to-last `#join p.note` ends with `The hub itself (verify-hub-<id>) refuses to join.` On a run started with `CIDER_BUILD_EXCLUDE=my-laptop hubctl.py up` it ends with `The hub itself (verify-hub-<id>) and my-laptop, in the hub's exclude setting, refuse to join.`
- **Copy.** Run `t.click("#join .cmd button", "Copy")`. A toast reads `Copied.`, or `Selected: copy it with Ctrl+C (⌘C on a Mac).` when the clipboard is unavailable.
- **Join script.** Run `curl -fsS http://127.0.0.1:<tailnet port>/join | head -4` in a terminal. Its first three lines include `#!/usr/bin/env bash` and `export CIDER_BUILD_HUB=https://verify-hub-<id>.example.ts.net:<port>`.
- **Proof.** Take screenshots of both views and save the `/join` head in the journal or a file in the evidence dir.

## Gotchas

- In the seed, a done job's drawer Download usually points at an artifact that is not cached (finished jobs have keys from `k0003` up). Assert on the link text and href; fetching it from the page logs a 404 console error.
- The tailnet port of a seeded run is in `/tmp/verify-hub/run-<id>/state.json` (`tailnet_port`), not in the URL.
- Never pipe the `/join` script into `bash` on this machine. It installs a builder agent. Read it only.
- In headless Chrome the clipboard API may be refused. Then the panel falls back to selecting the text, and both toasts are correct behaviour. Assert that one of them appears.
- On the real hub (`up --real`) the commands show the real tailnet IP and name, which is a read-only check that is worth doing after a hub change.
