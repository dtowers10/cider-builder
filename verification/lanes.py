#!/usr/bin/env python3
"""Which verification a change needs, and whether the verification itself has drifted from the code.

    verification/lanes.py [BASE]    the lanes the changes since BASE need (default: the merge-base with main),
                                    working tree and untracked files included; always exits 0
    verification/lanes.py --check   drift between the code, CI and the verification skills; exits 1 on any

The protocol lane is decided against the model's sync commit, not BASE: it names every function in the
coverage table of .claude/skills/verify-job-protocol/SKILL.md that changed since the model was last confirmed.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_SKILL = ROOT / ".claude/skills/verify-job-protocol/SKILL.md"
HUB_SKILL = ROOT / ".claude/skills/verify-hub"
CI = ROOT / ".github/workflows/ci.yml"
HELPERS = {"lanes.py", "trace.py"}

LANES = {
    "protocol": "run /pstack:maintain-formal-verification-skill on the verify-job-protocol skill: the TLA+ model "
    "must describe the changed functions, verification/verify.sh must pass, and the sync commit moves",
    "panel": "run /pstack:maintain-verification-skill on the verify-hub skill: a new panel feature gets a "
    "features/*.md entry, a journey, and a row in features/README.md, all driven live",
    "tests": "run every verification/*.py test (the CI hub job); new HTTP, CLI or install behaviour gets a check "
    "in the script that owns it, or a new script added to ci.yml and docs/verification.md",
    "lint": "bash -n, shellcheck and py_compile, as the CI lint job does",
}

PATH_LANES = [
    ("bin/cider-build-panel.html", {"panel"}),
    ("bin/cider-build-hub", {"tests"}),
    ("bin/cider-build-worker", {"tests"}),
    ("bin/cider-build", {"tests"}),
    ("bin/build.sh", {"tests", "protocol"}),
    ("install.sh", {"tests"}),
    ("docs/configuration.md", {"tests"}),
    ("verification/JobProtocol.tla", {"protocol"}),
    ("verification/MC.tla", {"protocol"}),
    ("verification/cfg/", {"protocol"}),
    ("verification/verify.sh", {"protocol"}),
    ("verification/", {"tests"}),
    (".claude/skills/verify-hub/", {"panel"}),
]
SCRIPTS = ("bin/", "install.sh", "verification/")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def sync_commit():
    m = re.search(r"\*\*Sync commit:\*\* `([0-9a-f]{7,40})`", PROTOCOL_SKILL.read_text())
    return m.group(1)


def covered():
    """{file: {qualified function name}} from the coverage table's first column."""
    out = {}
    for line in PROTOCOL_SKILL.read_text().splitlines():
        m = re.match(r"\| `(bin/[^`]+)`:([^|]*)\|", line)
        if m:
            names = re.findall(r"`([A-Za-z_][\w.]*)\(\)`", m.group(2))
            out.setdefault(m.group(1), set()).update(names)
    return out


def functions(path):
    """[(first line, last line, qualified name)] for every def in a Python file, innermost last."""
    tree = ast.parse((ROOT / path).read_text())
    spans = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                if not isinstance(child, ast.ClassDef):
                    spans.append((child.lineno, child.end_lineno, name))
                walk(child, name + ".")

    walk(tree, "")
    return spans


def changed_lines(base, path):
    lines = set()
    for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", git("diff", "-U0", base, "--", path), re.M):
        start, count = int(m.group(1)), int(m.group(2) or 1)
        lines.update(range(start, start + max(count, 1)))
    return lines


def changed_files(base):
    files = set(git("diff", "--name-only", base).split())
    files |= set(git("ls-files", "--others", "--exclude-standard").split())
    return sorted(files)


def stale_protocol_functions():
    sync = sync_commit()
    stale = []
    for path, names in sorted(covered().items()):
        if not (ROOT / path).exists() or not git("diff", "--name-only", sync, "--", path).strip():
            continue
        if path.endswith(".sh"):
            stale.append("%s (any change since %s)" % (path, sync[:7]))
            continue
        lines = changed_lines(sync, path)
        for first, last, name in functions(path):
            if name in names and lines & set(range(first, last + 1)):
                stale.append("%s: %s()" % (path, name))
    return stale


def lanes(base):
    files = changed_files(base)
    needed = {}
    for f in files:
        for prefix, ls in PATH_LANES:
            if f == prefix or (prefix.endswith("/") and f.startswith(prefix)):
                for lane in ls:
                    needed.setdefault(lane, set()).add(f)
                break
        if f.startswith(SCRIPTS) and (ROOT / f).is_file() and (ROOT / f).read_bytes()[:2] == b"#!":
            needed.setdefault("lint", set()).add(f)
    stale = stale_protocol_functions()
    if stale:
        needed.setdefault("protocol", set()).update(stale)
    print("Changes since %s: %d file(s)" % (base[:12], len(files)))
    for lane in LANES:
        if lane in needed:
            print("\n[%s] %s" % (lane, LANES[lane]))
            for why in sorted(needed[lane]):
                print("    " + why)
    if not needed:
        print("No verification lane applies. Say so in the PR.")
    print("\nThen: verification/lanes.py --check")


def check():
    problems = []

    ci = CI.read_text()
    tests = {p.name for p in (ROOT / "verification").glob("*.py")} - HELPERS
    in_ci = set(re.findall(r"verification/([\w-]+\.py)", ci)) - HELPERS
    problems += ["%s is not run by %s" % (t, CI.relative_to(ROOT)) for t in sorted(tests - in_ci)]
    problems += ["%s names verification/%s, which does not exist" % (CI.relative_to(ROOT), t)
                 for t in sorted(in_ci - tests)]

    journeys = {p.name for p in (HUB_SKILL / "journeys").glob("*.mjs")}
    index = (HUB_SKILL / "features/README.md").read_text()
    table = {j for row in index.splitlines() if row.startswith("|")
             for j in re.findall(r"journeys/([\w-]+\.mjs)", row)}
    problems += ["journeys/%s is missing from the table in verify-hub/features/README.md" % j
                 for j in sorted(journeys - table)]
    for md in sorted(HUB_SKILL.rglob("*.md")):
        for j in sorted(set(re.findall(r"journeys/([\w-]+\.mjs)", md.read_text())) - journeys):
            problems.append("%s names journeys/%s, which does not exist" % (md.relative_to(ROOT), j))

    sync = sync_commit()
    if subprocess.run(["git", "merge-base", "--is-ancestor", sync, "HEAD"], cwd=ROOT,
                      capture_output=True).returncode != 0:
        problems.append("the protocol sync commit %s is not an ancestor of HEAD; point it at a commit on this "
                        "branch's history" % sync[:12])

    for path, names in sorted(covered().items()):
        if path.endswith(".sh"):
            continue
        defined = {name for _, _, name in functions(path)}
        problems += ["coverage table names %s: %s(), which is no longer defined there" % (path, n)
                     for n in sorted(names - defined)]

    for p in problems:
        print("DRIFT " + p)
    print("RESULT %s (%d problem(s))" % ("fail" if problems else "pass", len(problems)))
    return 1 if problems else 0


def main(argv):
    if argv[:1] == ["--check"]:
        return check()
    base = argv[0] if argv else git("merge-base", "HEAD", "origin/main" if git("branch", "--list", "main") == ""
                                    else "main").strip()
    lanes(base)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
