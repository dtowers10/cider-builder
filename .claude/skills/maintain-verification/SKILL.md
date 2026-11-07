---
name: maintain-verification
description: Closes out any change to Cider Builder (a new feature, a fix, a refactor) by running the verification it needs and keeping that verification, CLAUDE.md and the docs in step with the code. Use it before you call a change done or open a PR, and whenever verification/lanes.py --check fails. It routes to verify-job-protocol (TLA+) and verify-hub; it does not replace them.
metadata:
  internal: true
---

# Maintain verification

The repository has four verification lanes. `verification/lanes.py` decides which ones a change needs, so never pick them by hand.

## 1. Route

```bash
verification/lanes.py            # lanes for everything since the merge-base with main, uncommitted files included
verification/lanes.py <rev>      # since another base
```

Run every lane it prints. If it prints none, say so in the PR.

| Lane | What to do |
|---|---|
| `protocol` | Follow `.claude/skills/verify-job-protocol/SKILL.md`, "When you change the code on purpose". It names each covered function changed since the model's sync commit. Update `verification/JobProtocol.tla`, run `verification/verify.sh` until it exits 0, then advance the sync commit in that skill to the commit the model now describes. A new guard that protects a property gets a mutant in `verify.sh`. |
| `panel` | Follow `.claude/skills/verify-hub/SKILL.md`. Run the journeys of every feature you touched. A new panel feature gets a sub-feature line in its `features/*.md`, a journey in `journeys/`, and that journey in the table of `features/README.md`. |
| `tests` | Run every `verification/*.py` test that CI runs (the `hub` job in `.github/workflows/ci.yml`). New HTTP, CLI, config or install behaviour gets a check in the script that already owns that area. A new script goes into `ci.yml` and gets a paragraph in `docs/verification.md`. |
| `lint` | `bash -n` and `shellcheck --severity=warning` on shell scripts, `python3 -m py_compile` on Python, as the CI `lint` job does. |

Do not weaken a property, a check or a journey to make it pass. A failure the code causes is a finding. Report it with its evidence.

## 2. Record

- **CLAUDE.md.** Update it when the change adds a part, a command, a lane, a setting or a rule a future session needs before it reads code. Keep it a map that points at docs and skills. Do not copy their content into it.
- **Docs.** A new user-facing behaviour belongs in `README.md` or the matching `docs/*.md`. A new setting belongs in `docs/configuration.md`; `verification/hub-config.py` fails without it.
- **Lanes.** A new top-level file under `bin/`, or a new kind of verification, needs a row in `PATH_LANES` or `LANES` in `verification/lanes.py`.

## 3. Check

```bash
verification/lanes.py --check    # exit 0, RESULT pass
```

It fails when a `verification/*.py` test is not in CI, when a journey is missing from the verify-hub table or a doc names one that does not exist, when the protocol sync commit is not in this branch's history, or when the coverage table names a function the code no longer defines. CI runs the same check on every PR.

## Report

In the PR description, list each lane `lanes.py` printed and its evidence: the `verify.sh` summary line, each journey's `RESULT` line, the test scripts that ran and their exit codes. Name any lane you skipped and why.
