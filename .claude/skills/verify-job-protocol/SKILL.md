---
name: verify-job-protocol
description: Checks with TLA+/TLC the job protocol between the hub (bin/cider-build-hub) and the agents on the Macs (bin/cider-build-worker). Use it before accepting any change to the queue, Mac assignment, heartbeats, retries, cancellation, result delivery or the cleanup of a Run, and whenever you need to reason about what happens with network partitions, restarts or Ctrl-C in the middle of a build.
metadata:
  internal: true
---

# Verify the job protocol

`verification/JobProtocol.tla` models how a job moves from `queued` to `assigned`, `building` and finally `done`, `failed` or `cancelled`. It also models how each agent receives it, builds it, delivers it and cleans it up. TLC explores every possible ordering of those steps within small bounds, including network partitions, agent restarts, lost responses and cancellations at any moment.

## When to use it

Use this skill if your change touches any function in the coverage table, or changes the meaning of a field in `jobs/<id>.json` or `workers/<mac>.json`. If it touches none, there is no need.

To find out, compare what changed since the sync commit:

```bash
git diff --stat <sync commit> -- bin/
```

## How to run it

```bash
verification/verify.sh                    # about 30 s; exits 0 if everything is as expected
verification/verify.sh trace <Invariant>  # shortest counterexample for that property, step by step
verification/run-order.py [<rev>]         # the NoFalseFailure ordering locally, with the real hub, agent and build.sh
```

It needs Java 11 or later and downloads TLC v1.7.4, the latest stable release, pinned by sha256 in the script.

How to read the output:

- **"Holds, N slot(s) … OK (M distinct states found)".** These properties hold in every reachable state within the bounds:
  - `HubSlots`. The hub never assigns a Mac more jobs than it has slots.
  - `BuildSlots`. A Mac never runs more concurrent builds than it has slots, not even after cancelling one.
  - `OneActivePerKey`. There are never two active jobs with the same project, key and platform.
  - `CacheFromCurrentAttempt`. What enters `cache/` is the artifact of the current attempt of a finished job.
  - `NoFalseFailure`. A successful build never ends up marked failed.
  - `SourceBeforeAssign`. A job reaches a Mac only once its whole source is on the hub, whether it was uploaded whole or rebuilt from a delta.
- **"Known finding X reproduces (expected)".** A defect already documented below that is still in the code. If it says "NO LONGER REPRODUCES", someone fixed it. Move that invariant to `cfg/holds.cfg`, delete its `cfg/finding-X.cfg`, remove it from `FINDINGS` in `verify.sh` and update the findings section.
- **"Mutant … detected".** Each mutant removes a guard from the model, and the matching property has to fail. If it says "NOT DETECTED", that property no longer protects anything. Fix it before you trust an OK.

To read any TLC result, counterexample or clean pass, use pstack's `/statechart` skill. It shows each violation as its shortest path in words, and for a clean pass it draws how the system moves between states. `verification/trace.py` gives a quick per-step summary with the variables that change.

## If something fails: real bug or model error?

Read the counterexample step by step and find each step in the code, using the coverage table.

- **Real bug.** Every step can happen in the code in that order, timeouts included.
- **Model error.** Some step cannot happen that way in the code. It happened once: the model let `LOST_TTL` (60 s) expire with a heartbeat response still in flight, but `main()` cuts the request off at 15 s. Fix it in the model and leave a comment citing the line of code that justifies it.

Timeouts are not clocks in the model but conditions:

| Timeout | Value | Condition in the model |
|---|---|---|
| `BEAT_TTL` | 30 s | `fresh` |
| `LOST_TTL` | 60 s | `LostTimeout` |
| `SOURCE_TTL` | 120 s | `SourceTimeout` |
| Agent heartbeat timeout | 15 s | `resp` |
| Lock polling in `build.sh` | 15 s | Not modeled |

If a counterexample depends on a long timeout expiring before a short one, check that this is possible in the code.

Do not weaken a property or the model to make it pass. If the code breaks a property, that is a finding. Report it with its counterexample in terms of the code, and do not change product code unless the user asks for it.

## When you change the code on purpose

1. Find in the coverage table the model action that matches each function you change.
2. Change that action so it does the same as the new code. Keep the atomicity rule:
   - What the hub does under a single `with lock:` is a single action.
   - In the agent, each `Run` phase is an action.
   - If the new code releases the lock midway, as `Handler.result()` does while receiving the artifact, split the action.
3. If the change fixes a finding, follow the "NO LONGER REPRODUCES" steps above.
4. If you add a new guard that protects a property, add its mutant in `verify.sh`.
5. Run `verification/verify.sh` until it exits 0.
6. Advance the sync commit below only once you have confirmed that the model describes the code at that commit.

## Coverage

| Code | Model action or definition |
|---|---|
| `bin/cider-build-hub`: `submit()`, with or without a waiter (`cider-build warm` sends none and marks the job `warm`) | `Submit` |
| `bin/cider-build-hub`: `got_source()`, from `Handler.upload_source()` (whole tarball) and `Handler.upload_delta()` (rebuilt from the base tree) | `Upload`. `source_manifest()`, `rebuild()`, `seed_base()` and a delta the hub refuses change no job state, so they are not actions |
| `bin/cider-build-hub`: `detach()` (last client of a job that is not `warm`, or `all=1` from the panel, which removes them all). A client leaving a `warm` job cancels nothing, which in the model is a stutter step | `Detach` |
| `bin/cider-build-hub`: `recover()` | `SourceTimeout`, `LostTimeout`. `SourceTimeout` fires whenever the job lacks source; the code also waits for any open upload (`Handler.carrying_source`), which the model does not need |
| `bin/cider-build-hub`: `lose()` | `Lost` |
| `bin/cider-build-hub`: `schedule()`, `schedulable()`, `used()` | `Schedule`, `Used`, `fresh`, `Stale`. The filter on `w["running"]` from the last heartbeat is `j \notin Ids(w)` in `Schedule` (the comment on `Schedule` explains why they are equivalent). `schedulable()` also skips a Mac that `refusal()` names, one in `drained`, and one whose agent the panel asked to update (`w["update"]`). Those filters only remove Macs, and `Schedule` allows any Mac |
| `bin/cider-build-hub`: `heartbeat()` and `running` in `workers/<mac>.json` | `Beat`, `listed` |
| `bin/cider-build-hub`: `worker_job()` | `Owns` |
| `bin/cider-build-hub`: `Handler.result()`, `move()`, `TRANSITIONS` | `Report` (the second call to `worker_job()`, under the lock, decides) |
| `bin/cider-build-worker`: `main()` | `Recv`, `DropResp` and the `running` list that `Beat` sends |
| `bin/cider-build-worker`: `Run.build()`, `Run.download()` | `Fetch`, `Finish` |
| `bin/cider-build-worker`: `Run.send_log()` | `LogGone` |
| `bin/cider-build-worker`: `Run.cancel()`, `kill_group()` | `Killed` |
| `bin/cider-build-worker`: `Run.report()` | `Report`, `GiveUp` |
| `bin/cider-build-worker`: the `out` path of `Run.run()`, which `build.sh` receives in `OUT` | `OutPath` |
| `bin/cider-build-worker`: `finally` of `Run.run()` | `Cleanup` and the `outFile` cleanup in `Report` and `GiveUp` |
| `bin/cider-build-worker`: `reap()` and the new `BOOT` | `Restart` |
| `bin/cider-build-worker`: `update_agent()` and the `os._exit(0)` after it in `main()`, only when no Run is active | `Restart`, which the model allows at any moment |
| `bin/build.sh`: lock `~/builds/.lock-$PROJ-$PLAT` and `$OUT` | `TakeLock`, `lockOwner`, `outFile` |

**Outside the model:**
- FIFO order and the choice by affinity or free RAM. The model lets any job go to any Mac, which is more permissive.
- Several clients waiting for the same job. The model treats `Detach` as if the last one left.
- Whether a job is `warm`. The model lets `Detach` cancel any active job, which is more permissive than the code.
- Client expiry (`WAITER_TTL`), deletion of old jobs (`KEEP_S`) and `refresh_drained()`.
- `load()` after a hub restart. The hub resumes its state from disk, and in the model that changes nothing.
- The log chunk that gets resent.
- The `bin/cider-build` client, except `submit`, the upload and `detach`. Whether the upload was whole or incremental, and the fallback between them, is outside: only the moment `src` becomes TRUE counts.
- The base trees in `bases/` (`base_lock`). They decide only whether a delta can be rebuilt, never a job's state. `verification/source-delta.py` checks them with the real client, hub and agent.
- The gap between `Popen` and writing the pidfile in `Run.build()`.
- The Mac details sent in the heartbeat (`info`, from `host_info()` in the agent and `clean_info()` in the hub). They are only stored and shown in `status()`, with no effect on the queue or on assignment.
- Listening on the tailnet IP (`listen_tailnet()`) and `/join`. They use the same `Handler` as 127.0.0.1.
- Agent updates from the panel: `request_update()`, `agent_version()`, and the `update`, `self_update` and `update_error` fields in `heartbeat()`. They change no job and no `running` list. The agent's exit after an update is a `Restart`.
- Hub updates (`update_release()`): the hub exits with the lock held and no transfer in flight, and launchd starts it again. That is a hub restart, the same as `load()`.

**Bounds:**

| Configuration | Macs | Slots | Keys | Jobs | Retries | Starts per agent |
|---|---|---|---|---|---|---|
| `cfg/holds.cfg` | 1 | 1 | 2 | 2 | 1 | 2 |
| `cfg/holds.cfg` with 2 slots, without `HubSlots` or `BuildSlots` | 1 | 2 | 2 | 2 | 1 | 2 |
| `cfg/finding-*.cfg` | 1 | 2 | 2 | 2 | 1 | 2 |

With 1 slot, `used()` keeps the same Mac from getting a job again while the agent still names its old Run. That is why the findings that depend on it, and the `attempt` mutant, run with 2 slots. With 2 jobs and 2 slots, `HubSlots` and `BuildSlots` cannot fail, so that pass does not check them.

`cfg/holds.cfg` has symmetry between keys. A pass with 2 Macs does not finish in useful time: it went past 45 million states without finishing. An OK covers these bounds, not the whole system.

**Sync commit:** `5acd86fadd7f5ed87ee3cf4b7f14e260e52f53f4`. The last commit at which the model was confirmed to describe the functions in the table.

## Known findings (with the code at the sync commit)

None. `RunMatchesAttempt`, `BuildSlots` and `NoFalseFailure` were findings and now hold. If a new property fails with the current code and the fix is not immediate, document it here with its counterexample in terms of the code, create its `cfg/finding-X.cfg` and add it to `FINDINGS` in `verify.sh`.
