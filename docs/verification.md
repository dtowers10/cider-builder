# Verification

`verification/verify.sh` uses TLC (TLA+) to check every possible ordering of submit, assignment, heartbeats, network partitions, agent restarts, cancellations and deliveries, within small bounds. It takes about 30 s.

**These hold:**
- The hub never exceeds a Mac's slots.
- A Mac never runs more builds than slots, not even after a Ctrl-C: the slot stays taken until the agent stops naming the cancelled build.
- There are never two active jobs for the same version.
- Only the artifact of the current attempt enters the cache.
- A successful build never ends up marked failed, not even if it is relaunched right away on the same Mac.

**Known findings:** none. The three the model found (a retry spent after a network partition, one build too many after a Ctrl-C and a successful build marked failed) are fixed and are now checked as properties.

`verification/run-order.py` reproduces locally, with the real hub, agent and `build.sh`, the Ctrl-C-and-relaunch ordering on the same Mac. It needs python3, rsync and git, and does not touch the fleet.

`verification/hub-update.py` updates a hub installed in a temporary folder from a local git repository, its `update_url`, with the hub replacing its own running files. It also checks that a commit that does not compile, does not start, or cannot read the live `hub.json` is refused without touching anything. Then it updates agents over HTTP and with the real `cider-build-worker`.

`verification/hub-smoke.py` starts the hub locally with no Macs and no tailnet, and checks what clients, Macs and the browser see: `/status`, the panel with its CSP, `/join` and `/bin/install.sh` pointed at the hub, which Macs the hub refuses, a Mac out of the pool, a Mac's slots, one build cycle all the way to the cache, and hub updates off with no update source.

`verification/hub-config.py` checks the hub's settings: defaults, `hub.json` against the environment, every value the hub refuses, `cider-build-hub config get|set`, and that [docs/configuration.md](configuration.md) lists every setting.

`verification/install-client.py` installs a client from a hub with an empty home, as a stranger would (`curl <hub>/bin/install.sh | bash -s client`), then runs `cider-build` with no `CIDER_BUILD_HUB`, and checks where `add`, `remove` and `hub-install` would connect, and that `hub-install` passes the clone's remote and branch.

`verification/install-hub.py` runs `install.sh hub` on Linux with fakes for the macOS tools, from a scratch clone and from a plain copy, and checks which update source each install leaves in `hub.json`: the clone's remote with no decision, `off` kept across reinstalls, `--set update_url` first, a plain copy off, the deploy key created once for ssh, and no token printed.

`verification/waiter-ttl.py` runs the real client against a local hub that stops hearing it for longer than `WAITER_TTL`. It checks that the client gives up before the hub forgets it, so another developer's Ctrl-C never cancels the build it is still waiting for, and that this Ctrl-C does cancel once the client is gone. It takes about 2.5 min, and `--rev main` runs it with an earlier client.

`verification/source-delta.py` runs the real client, hub, agent and `build.sh` locally and checks the incremental upload: a first full upload, a second one after changing one file that sends far fewer bytes, that the agent unpacks exactly the client's tree in both cases, and the fallback when the hub's base is corrupt. With `--measure` it times a bigger project behind a throttled link, and `--rev main` does the same with an earlier version for comparison.

`verification/source-ttl.py` runs the hub locally with the 2-minute source timeout lowered to 4 s and checks that a slow whole or incremental upload is accepted, and that a job is cancelled when its client never uploads, dies mid-upload or goes silent mid-upload. `--rev main` runs it against an earlier hub.

`verification/warm-upload.py` runs the real client and hub with a 10 s `SOURCE_TTL` and checks `cider-build warm`: a full and an incremental upload slower than the TTL keep their job, an upload that stops sending and a job that never gets a byte are cleaned up, and a warm-up cancelled from the panel mid-upload says so.

GitHub Actions (`.github/workflows/ci.yml`) runs, on every PR and every push to `main`, the script lint (which also rejects any `*.ts.net` name other than `example.ts.net`), `verify.sh` and the ten hub tests, with Python 3.9.

The details, the coverage and how to maintain the model are in `.claude/skills/verify-job-protocol/SKILL.md`.
