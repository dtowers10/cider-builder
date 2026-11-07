# Cider Builder

Builds iOS and Android apps on a fleet of Macs. A hub (`bin/cider-build-hub`) owns the queue, the Macs and the cache, and serves a web panel (`bin/cider-build-panel.html`). Each Mac runs an agent (`bin/cider-build-worker`) that runs `bin/build.sh`. Clients run `bin/cider-build`. `install.sh` installs all three. The README's Development table says what each file does.

Bash and Python 3.9, standard library only. Keep it that way: CI compiles every script with Python 3.9.

## Verification

Every change ends with the `maintain-verification` skill (`.claude/skills/maintain-verification/SKILL.md`). Start it with:

```bash
verification/lanes.py            # which verification this change needs
verification/lanes.py --check    # whether the verification still matches the code; CI runs it too
```

It routes to these:

- `.claude/skills/verify-job-protocol/` checks the hub and agent job protocol with TLA+ (`verification/verify.sh`). Any change to the queue, assignment, heartbeats, retries, cancellation, result delivery or Run cleanup needs it.
- `.claude/skills/verify-hub/` drives the panel and `cider-build status` against a disposable seeded hub.
- `verification/*.py` are the hub, client and install tests. They run on Linux with fakes and touch no network. `docs/verification.md` describes each one.

A feature is not done until its lanes pass and this file, the docs and the verification skills describe it.

## Rules

- Never write a tailnet name other than `example.ts.net`. CI rejects it.
- Every hub setting is listed in `docs/configuration.md`. `verification/hub-config.py` fails otherwise.
- Never weaken a TLA+ property, a test or a journey to make it pass. Report the failure as a finding.
