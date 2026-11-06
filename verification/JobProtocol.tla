---------------------------- MODULE JobProtocol ----------------------------
(* Job protocol between the hub (bin/cider-build-hub) and the agents on the Macs
   (bin/cider-build-worker). Each action is one indivisible step of the code: what the hub does
   under its `lock` is a single step; in the agent, each `Run` thread advances through phases.
   Time does not exist: the timeouts (BEAT_TTL 30 s, LOST_TTL 60 s, SOURCE_TTL 120 s) are
   enabling conditions, not clocks. *)
EXTENDS Naturals, FiniteSets

CONSTANTS Workers, Slots, Keys, MaxJobs, MaxRetries, MaxBoots

None == "none"
Active == {"queued", "assigned", "building"}          \* ACTIVE in cider-build-hub
OnWorker == {"assigned", "building"}                  \* ON_WORKER
JobIds == 1..MaxJobs
Phases == {"fetch", "wait", "build", "dead", "report"}
(* phase of an agent Run:
   fetch  = Run.download + tar, no process yet
   wait   = build.sh started, waiting for the lock ~/builds/.lock-<proj>-<plat>
   build  = build.sh holds the lock, building
   dead   = process killed by cancellation; the thread has not gone through Run.run's `finally` yet
   report = build.sh finished; Run.report delivers the result *)

VARIABLES
    jobs,      \* hub: jobs/<id>.json
    njobs,     \* hub: jobs created
    fresh,     \* hub: the Mac sent a heartbeat < BEAT_TTL ago (part of `schedulable`)
    listed,    \* hub: `running` in workers/<mac>.json, what the Mac named and what it was handed
    runs,      \* agent: `running`, one Run per job
    boot,      \* agent: BOOT, changes on every start
    resp,      \* /w/heartbeat response in flight to the agent
    down,      \* the Mac cannot reach the hub (network partition)
    lockOwner, \* Mac: who holds ~/builds/.lock-<proj>-<plat>
    outFile,   \* Mac: who wrote each file in ~/builds/out
    written,   \* ghost: artifacts the hub put into cache/
    falseFail  \* ghost: a successful build ended up marked failed

vars == <<jobs, njobs, fresh, listed, runs, boot, resp, down, lockOwner, outFile, written, falseFail>>

Tag(r) == <<r.id, r.attempt>>
NoTag == <<>>
KeyOf(r) == jobs[r.id].key
Ids(w) == {r.id : r \in runs[w]}
\* used(): the jobs the hub assigns to it and the ones the agent may still have running
Used(w) == Cardinality({j \in JobIds : jobs[j].state \in OnWorker /\ jobs[j].worker = w} \cup listed[w])
Mine(j, w) == jobs[j].state \in OnWorker /\ jobs[j].worker = w
\* worker_job(): the Mac, the attempt and the state must match
Owns(r, w) == Mine(r.id, w) /\ jobs[r.id].attempt = r.attempt
Replace(S, a, b) == (S \ {a}) \cup {b}
\* Run.run() picks the artifact path and build.sh receives it in OUT:
\* ~/builds/out/<proj>-<key>-<plat>-<id>-<attempt>.<ext>, one per attempt
OutPath(r) == Tag(r)
\* Schedule bumps attempt only from the queue, and a job returns to the queue at most MaxRetries times
OutPaths == Keys \cup (JobIds \X (1..(MaxRetries + 1)))

\* lose()
Lost(rec) == IF rec.retries >= MaxRetries
             THEN [rec EXCEPT !.state = "failed"]
             ELSE [rec EXCEPT !.state = "queued", !.worker = None, !.retries = @ + 1]

Init ==
    /\ jobs = [j \in JobIds |-> [key |-> None, state |-> "free", worker |-> None, attempt |-> 0,
                                 retries |-> 0, src |-> FALSE, delivered |-> 0]]
    /\ njobs = 0
    /\ fresh = [w \in Workers |-> TRUE]
    /\ listed = [w \in Workers |-> {}]
    /\ runs = [w \in Workers |-> {}]
    /\ boot = [w \in Workers |-> 1]
    /\ resp = [w \in Workers |-> {}]
    /\ down = [w \in Workers |-> FALSE]
    /\ lockOwner = [w \in Workers |-> [k \in Keys |-> NoTag]]
    /\ outFile = [w \in Workers |-> [p \in OutPaths |-> NoTag]]
    /\ written = {}
    /\ falseFail = FALSE

---------------------------------------------------------------------------
\* Clients (bin/cider-build) against the hub

\* submit(): if there is an active job with the same key, the client joins it (no change)
Submit(k) ==
    /\ njobs < MaxJobs
    /\ ~\E j \in JobIds : jobs[j].state \in Active /\ jobs[j].key = k
    /\ njobs' = njobs + 1
    /\ jobs' = [jobs EXCEPT ![njobs + 1] = [@ EXCEPT !.key = k, !.state = "queued"]]
    /\ UNCHANGED <<fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* got_source(), from Handler.upload_source() (whole tarball) or Handler.upload_delta() (the hub rebuilt
\* it from its base tree and the client's changes, outside the lock, before this step). Either way `src`
\* becomes TRUE in this one step under the lock, only for a queued job, and only once the whole
\* .src.tar.gz exists. POST /source/manifest and a failed delta change no job state.
Upload(j) ==
    /\ jobs[j].state = "queued" /\ ~jobs[j].src
    /\ jobs' = [jobs EXCEPT ![j].src = TRUE]
    /\ UNCHANGED <<njobs, fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* recover(): SOURCE_TTL. The code waits while a request carrying the source is open and counts from the end
\* of the last one (Handler.carrying_source); here it may fire at any moment the job lacks source, which is
\* more permissive.
SourceTimeout(j) ==
    /\ jobs[j].state = "queued" /\ ~jobs[j].src
    /\ jobs' = [jobs EXCEPT ![j].state = "cancelled"]
    /\ UNCHANGED <<njobs, fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* detach() by the last waiting client (Ctrl-C)
Detach(j) ==
    /\ jobs[j].state \in Active
    /\ jobs' = [jobs EXCEPT ![j].state = "cancelled"]
    /\ UNCHANGED <<njobs, fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

---------------------------------------------------------------------------
\* Hub

\* schedule(): any queued job with source, to any `schedulable` Mac that does not list
\* that id in its last heartbeat (the affinity or free-RAM preference and FIFO order do not change
\* the properties). The hub looks at w["running"] from the last heartbeat and the model at the agent's Runs:
\* they differ only in a Run the agent created after that heartbeat, and then the job is on the
\* Mac (not queued) or the Mac is not `fresh` until the next heartbeat
Schedule(j, w) ==
    /\ jobs[j].state = "queued" /\ jobs[j].src
    /\ fresh[w] /\ Used(w) < Slots[w]
    /\ j \notin Ids(w)
    /\ jobs' = [jobs EXCEPT ![j].state = "assigned", ![j].worker = w,
                            ![j].attempt = @ + 1, ![j].delivered = 0]
    /\ UNCHANGED <<njobs, fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* heartbeat(): the agent sends its `running` list; the hub processes it under the lock
Beat(w) ==
    /\ ~down[w] /\ resp[w] = {}
    /\ LET S == Ids(w)
           a1 == [j \in JobIds |-> IF j \in S /\ Mine(j, w) /\ jobs[j].state = "assigned"
                                   THEN [jobs[j] EXCEPT !.state = "building"] ELSE jobs[j]]
           a2 == [j \in JobIds |-> IF Mine(j, w) /\ j \notin S /\ a1[j].delivered # 0
                                      /\ a1[j].delivered # boot[w]
                                   THEN Lost(a1[j]) ELSE a1[j]]
           out == {j \in JobIds : a2[j].state = "assigned" /\ a2[j].worker = w /\ j \notin S}
           a3 == [j \in JobIds |-> IF j \in out THEN [a2[j] EXCEPT !.delivered = boot[w]] ELSE a2[j]]
       IN /\ jobs' = a3
          /\ listed' = [listed EXCEPT ![w] = S \cup out]
          /\ resp' = [resp EXCEPT ![w] = {[cancel |-> {j \in S : ~Mine(j, w)},
                                           out |-> {<<j, a3[j].attempt>> : j \in out}]}]
    /\ fresh' = [fresh EXCEPT ![w] = TRUE]
    /\ UNCHANGED <<njobs, runs, boot, down, lockOwner, outFile, written, falseFail>>

\* recover(): LOST_TTL. Fires if the Mac has not named the job for 60 s: either it does not have it,
\* or it has sent no heartbeat for more than BEAT_TTL (network partition). A heartbeat response cannot
\* still be in flight after 60 s: the agent cuts it off at 15 s (http timeout in main())
LostTimeout(j) ==
    /\ jobs[j].state \in OnWorker
    /\ LET w == jobs[j].worker IN
          /\ resp[w] = {}
          /\ (down[w] /\ ~fresh[w]) \/ j \notin Ids(w)
    /\ jobs' = [jobs EXCEPT ![j] = Lost(@)]
    /\ UNCHANGED <<njobs, fresh, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* BEAT_TTL expired: the Mac stops being `schedulable`
Stale(w) ==
    /\ down[w] /\ fresh[w]
    /\ fresh' = [fresh EXCEPT ![w] = FALSE]
    /\ UNCHANGED <<jobs, njobs, runs, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

---------------------------------------------------------------------------
\* Agent (bin/cider-build-worker)

\* main(): applies `cancel` and starts a Run for each new job whose id it does not already have
Recv(w) ==
    /\ \E m \in resp[w] :
        runs' = [runs EXCEPT ![w] =
           {IF r.id \in m.cancel THEN [r EXCEPT !.cancelled = TRUE] ELSE r : r \in runs[w]}
           \cup {[id |-> o[1], attempt |-> o[2], phase |-> "fetch", cancelled |-> FALSE, rc |-> 0] :
                 o \in {o \in m.out : o[1] \notin Ids(w)}}]
    /\ resp' = [resp EXCEPT ![w] = {}]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, down, lockOwner, outFile, written, falseFail, listed>>

\* the heartbeat response is lost (the agent's 15 s timeout)
DropResp(w) ==
    /\ resp[w] # {}
    /\ resp' = [resp EXCEPT ![w] = {}]
    /\ UNCHANGED <<jobs, njobs, fresh, runs, boot, down, lockOwner, outFile, written, falseFail, listed>>

\* Run.build(): downloads the source; if the job already finished, /source returns 404 and the Run
\* delivers rc=1 (which the hub rejects); if it was cancelled during the download, build.sh does not start
Fetch(w, r) ==
    /\ r.phase = "fetch" /\ ~down[w]
    /\ runs' = [runs EXCEPT ![w] = Replace(@, r,
           IF r.cancelled THEN [r EXCEPT !.phase = "dead"]
           ELSE IF jobs[r.id].state \in Active THEN [r EXCEPT !.phase = "wait"]
           ELSE [r EXCEPT !.phase = "report", !.rc = 1])]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* build.sh: mkdir of the per-project, per-platform lock
TakeLock(w, r) ==
    /\ r.phase = "wait" /\ ~r.cancelled
    /\ lockOwner[w][KeyOf(r)] = NoTag
    /\ lockOwner' = [lockOwner EXCEPT ![w][KeyOf(r)] = Tag(r)]
    /\ runs' = [runs EXCEPT ![w] = Replace(@, r, [r EXCEPT !.phase = "build"])]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, outFile, written, falseFail, listed>>

\* build.sh finishes: with rc=0 it leaves the artifact in $OUT, and it releases the lock
Finish(w, r, rc) ==
    /\ r.phase = "build" /\ ~r.cancelled
    /\ lockOwner' = [lockOwner EXCEPT ![w][KeyOf(r)] = NoTag]
    /\ outFile' = IF rc = 0 THEN [outFile EXCEPT ![w][OutPath(r)] = Tag(r)] ELSE outFile
    /\ runs' = [runs EXCEPT ![w] = Replace(@, r, [r EXCEPT !.phase = "report", !.rc = rc])]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, written, falseFail, listed>>

\* Run.cancel(): SIGTERM to the process group; build.sh releases the lock in its EXIT trap
Killed(w, r) ==
    /\ r.phase \in {"wait", "build"} /\ r.cancelled
    /\ lockOwner' = IF lockOwner[w][KeyOf(r)] = Tag(r)
                    THEN [lockOwner EXCEPT ![w][KeyOf(r)] = NoTag] ELSE lockOwner
    /\ runs' = [runs EXCEPT ![w] = Replace(@, r, [r EXCEPT !.phase = "dead"])]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, outFile, written, falseFail, listed>>

\* Run.send_log(): /w/log returns 409 if the hub no longer assigns it that attempt, and the Run cancels itself
LogGone(w, r) ==
    /\ r.phase \in {"wait", "build"} /\ ~r.cancelled /\ ~down[w]
    /\ ~Owns(r, w)
    /\ runs' = [runs EXCEPT ![w] = Replace(@, r, [r EXCEPT !.cancelled = TRUE])]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, lockOwner, outFile, written, falseFail, listed>>

\* the `finally` of Run.run: deletes the artifact of its own attempt
Cleanup(w, r) ==
    /\ r.phase = "dead"
    /\ runs' = [runs EXCEPT ![w] = @ \ {r}]
    /\ outFile' = [outFile EXCEPT ![w][OutPath(r)] = NoTag]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, lockOwner, written, falseFail, listed>>

\* Run.report() + Handler.result() (the second worker_job, under the lock, is the one that decides)
\* and then the `finally` of Run.run
Report(w, r) ==
    /\ r.phase = "report" /\ ~down[w]
    /\ LET p == OutPath(r)
           ok == r.rc = 0 /\ outFile[w][p] # NoTag
       IN /\ IF Owns(r, w)
             THEN /\ jobs' = [jobs EXCEPT ![r.id].state = IF ok THEN "done" ELSE "failed"]
                  /\ written' = IF ok THEN written \cup {[job |-> r.id, attempt |-> r.attempt,
                                                         from |-> outFile[w][p]]}
                                ELSE written
                  /\ falseFail' = (falseFail \/ (r.rc = 0 /\ ~ok))
             ELSE UNCHANGED <<jobs, written, falseFail, listed>>
          /\ outFile' = [outFile EXCEPT ![w][p] = NoTag]
    /\ runs' = [runs EXCEPT ![w] = @ \ {r}]
    /\ UNCHANGED <<njobs, fresh, boot, resp, down, lockOwner, listed>>

\* Run.report() gives up after RESULT_PATIENCE without the hub
GiveUp(w, r) ==
    /\ r.phase = "report" /\ down[w]
    /\ runs' = [runs EXCEPT ![w] = @ \ {r}]
    /\ outFile' = [outFile EXCEPT ![w][OutPath(r)] = NoTag]
    /\ UNCHANGED <<jobs, njobs, fresh, boot, resp, down, lockOwner, written, falseFail, listed>>

\* the agent restarts: new BOOT, and reap() kills the builds and clears stage and out
Restart(w) ==
    /\ boot[w] < MaxBoots
    /\ boot' = [boot EXCEPT ![w] = @ + 1]
    /\ runs' = [runs EXCEPT ![w] = {}]
    /\ resp' = [resp EXCEPT ![w] = {}]
    /\ lockOwner' = [lockOwner EXCEPT ![w] = [k \in Keys |-> NoTag]]
    /\ outFile' = [outFile EXCEPT ![w] = [p \in OutPaths |-> NoTag]]
    /\ UNCHANGED <<jobs, njobs, fresh, down, written, falseFail, listed>>

\* network partition between the Mac and the hub, and its recovery
Partition(w) ==
    /\ down' = [down EXCEPT ![w] = ~@]
    /\ UNCHANGED <<jobs, njobs, fresh, runs, boot, resp, lockOwner, outFile, written, falseFail, listed>>

---------------------------------------------------------------------------

Next ==
    \/ \E k \in Keys : Submit(k)
    \/ \E j \in JobIds : Upload(j) \/ SourceTimeout(j) \/ Detach(j) \/ LostTimeout(j)
    \/ \E j \in JobIds, w \in Workers : Schedule(j, w)
    \/ \E w \in Workers :
          \/ Beat(w) \/ Stale(w) \/ Recv(w) \/ DropResp(w) \/ Restart(w) \/ Partition(w)
          \/ \E r \in runs[w] :
                \/ Fetch(w, r) \/ TakeLock(w, r) \/ Killed(w, r) \/ LogGone(w, r)
                \/ Cleanup(w, r) \/ Report(w, r) \/ GiveUp(w, r)
                \/ \E rc \in {0, 1} : Finish(w, r, rc)

Spec == Init /\ [][Next]_vars

---------------------------------------------------------------------------
\* Properties

TypeOK ==
    /\ njobs \in 0..MaxJobs
    /\ \A w \in Workers : listed[w] \subseteq JobIds
    /\ \A w \in Workers : \A r \in runs[w] : r.phase \in Phases

\* The hub never assigns a Mac more jobs than it has slots
HubSlots == \A w \in Workers : Used(w) <= Slots[w]

\* A Mac never runs more concurrent builds than it has slots
BuildSlots == \A w \in Workers : Cardinality({r \in runs[w] : r.phase = "build"}) <= Slots[w]

\* There are never two active jobs for the same project, key and platform
OneActivePerKey ==
    \A k \in Keys : Cardinality({j \in JobIds : jobs[j].state \in Active /\ jobs[j].key = k}) <= 1

\* What enters cache/ is the artifact of the current attempt of a finished job
CacheFromCurrentAttempt ==
    \A x \in written : /\ jobs[x.job].state = "done"
                       /\ jobs[x.job].attempt = x.attempt
                       /\ x.from = <<x.job, x.attempt>>

\* A successful build never ends up marked failed
NoFalseFailure == ~falseFail

\* A job reaches a Mac only once its whole source is on the hub (`src`), however it was uploaded
SourceBeforeAssign == \A j \in JobIds : jobs[j].state \in OnWorker \cup {"done"} => jobs[j].src

\* If the hub believes a Mac is working on a job and that Mac has a Run for that job,
\* it is the same attempt (otherwise that Run can never deliver, and the job waits 60 s and spends a retry)
RunMatchesAttempt ==
    \A w \in Workers : \A r \in runs[w] : Mine(r.id, w) => r.attempt = jobs[r.id].attempt

=============================================================================
