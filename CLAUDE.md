# Cider Builder

Builds iOS and Android apps on a fleet of Macs. A hub (`bin/cider-build-hub`) owns the queue, the Macs and the cache, and serves a web panel (`bin/cider-build-panel.html`). Each Mac runs an agent (`bin/cider-build-worker`) that runs `bin/build.sh`. Clients run `bin/cider-build`. `install.sh` installs all three. The README's Development table says what each file does.

Bash and Python 3.9, standard library only. Keep it that way: CI compiles every script with Python 3.9.

## Verification

Two project skills verify the code:

- `.claude/skills/verify-job-protocol/` checks the hub and agent job protocol with TLA+ (`verification/verify.sh`). It records the sync commit at which the model last matched the code.
- `.claude/skills/verify-hub/` drives the panel and `cider-build status` against a disposable seeded hub, from the feature map in `features/`.

`verification/*.py` are the hub, client and install tests. They run on Linux with fakes and touch no network. `docs/verification.md` describes each one.

### When you add a feature

1. Run `verification/lanes.py`. It prints the lanes the change needs since the merge-base with `main`.
2. For the `protocol` lane, run `/pstack:maintain-formal-verification-skill` on `verify-job-protocol`. It brings the TLA+ model in line with the changed functions, reruns `verify.sh`, reports drift and bugs separately, and moves the sync commit. Put that update in its own commit, apart from the product change.
3. For the `panel` lane, run `/pstack:maintain-verification-skill` on `verify-hub`. A new panel feature gets a `features/*.md` entry, a journey in `journeys/`, and a row in `features/README.md`, all driven live.
4. For the `tests` and `lint` lanes, run what `lanes.py` names.
5. Update this file when the feature adds a part, a command, a setting or a rule.
6. Run `verification/lanes.py --check`. It must print `RESULT pass`. CI runs it on every PR.

A feature is not done until these pass. If you cannot run a pstack skill as a slash command, read its `SKILL.md` in the pstack plugin and follow it.

## Rules

- Never write a tailnet name other than `example.ts.net`. CI rejects it.
- Every hub setting is listed in `docs/configuration.md`. `verification/hub-config.py` fails otherwise.
- Never weaken a TLA+ property, a test or a journey to make it pass. Report the failure as a finding.
