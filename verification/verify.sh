#!/usr/bin/env bash
# Checks the TLA+ model of the job protocol (JobProtocol.tla) with TLC.
#   ./verify.sh            properties that must hold + known findings + mutants
#   ./verify.sh trace INV  shortest counterexample for INV, step by step
# Exits 0 if everything is as expected: the properties hold, the known findings
# still reproduce and every mutant breaks the property it guards.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

TLA_VERSION=v1.8.0
TLA_SHA256=e20447644bfabd29d6bd0fc2c0eb1473fb301c1a0e4dfe1961938ce5a191edbf
JAR=tools/tla2tools.jar
FINDINGS=""

command -v java >/dev/null || { echo "Java 11 or later is missing." >&2; exit 2; }
if [ ! -f "$JAR" ] || [ "$(sha256sum "$JAR" | cut -d' ' -f1)" != "$TLA_SHA256" ]; then
  mkdir -p tools
  curl -fsSL -o "$JAR.tmp" "https://github.com/tlaplus/tlaplus/releases/download/$TLA_VERSION/tla2tools.jar"
  [ "$(sha256sum "$JAR.tmp" | cut -d' ' -f1)" = "$TLA_SHA256" ] || { echo "tla2tools.jar does not match the pinned sha256." >&2; exit 2; }
  mv "$JAR.tmp" "$JAR"
fi

tlc() { # dir cfg -> TLC output
  local dir=$1 cfg=$2 meta
  meta=$(mktemp -d)
  (cd "$dir" && java -XX:+UseParallelGC -cp "$OLDPWD/$JAR" tlc2.TLC -workers auto -deadlock -cleanup \
     -config "$cfg" -metadir "$meta" MC.tla 2>&1) || true
  rm -rf "$meta" "$dir"/MC_TTrace_*
}
verdict() { # output -> holds | violated:<inv> | error
  if grep -q "No error has been found" <<<"$1"; then echo holds
  elif inv=$(grep -oE "Invariant [A-Za-z]+ is violated" <<<"$1" | head -1 | cut -d' ' -f2) && [ -n "$inv" ]; then echo "violated:$inv"
  else echo error; fi
}

if [ "${1:-}" = trace ]; then
  inv=${2:?"Usage: ./verify.sh trace <Invariant>"}
  cfg=cfg/finding-$inv.cfg
  [ -f "$cfg" ] || { sed "s/^INVARIANTS.*/INVARIANTS $inv/; /^SYMMETRY/d" cfg/holds.cfg > "/tmp/verify-$inv.cfg"; cfg=/tmp/verify-$inv.cfg; }
  out=$(tlc . "$(readlink -f "$cfg")")
  echo "$(verdict "$out")"
  python3 trace.py <<<"$out"
  exit 0
fi

fail=0
report() { printf '%-52s %s\n' "$1" "$2"; }

# With 1 slot, used() keeps the same Mac from getting a job again while it still names the old Run;
# with 2 slots it can, and that shows which attempt enters the cache.
sed 's/MCSlots1/MCSlots2/; /^INVARIANTS/s/ HubSlots BuildSlots//' cfg/holds.cfg > /tmp/verify-holds2.cfg
for cfg in cfg/holds.cfg /tmp/verify-holds2.cfg; do
  out=$(tlc . "$(readlink -f "$cfg")")
  v=$(verdict "$out")
  states=$(grep -oE "[0-9]+ distinct states found" <<<"$out" | tail -1 || true)
  what="Holds, $(grep -oE 'MCSlots[0-9]' "$cfg" | tr -dc 0-9) slot(s)"
  if [ "$v" = holds ]; then report "$what" "OK ($states)"
  else report "$what" "FAIL: $v"; fail=1; python3 trace.py <<<"$out"; fi
done

for inv in $FINDINGS; do
  v=$(verdict "$(tlc . "$PWD/cfg/finding-$inv.cfg")")
  if [ "$v" = "violated:$inv" ]; then report "Known finding $inv" "reproduces (expected)"
  elif [ "$v" = holds ]; then report "Known finding $inv" "NO LONGER REPRODUCES: fixed? Move it to holds.cfg"; fail=1
  else report "Known finding $inv" "ERROR: $v"; fail=1; fi
done

# Mutants: each one removes a guard from the model that corresponds to a guard in the code.
# If the property does not fail with the guard removed, the check protects nothing.
mutant() { # name invariant slots original-text broken-text [original-text broken-text …]
  local d; d=$(mktemp -d)
  cp JobProtocol.tla MC.tla "$d/"
  python3 - "$d/JobProtocol.tla" "${@:4}" <<'PY'
import sys
p, args = sys.argv[1], sys.argv[2:]
s = open(p).read()
for a, b in zip(args[::2], args[1::2]):
    assert s.count(a) == 1, "the mutant no longer finds its text: " + a
    s = s.replace(a, b)
open(p, "w").write(s)
PY
  sed "s/^INVARIANTS.*/INVARIANTS $2/; s/MCSlots1/MCSlots$3/" cfg/holds.cfg > "$d/m.cfg"
  local v; v=$(verdict "$(tlc "$d" "$d/m.cfg")")
  rm -rf "$d"
  if [ "$v" = "violated:$2" ]; then report "Mutant $1" "detected by $2"
  else report "Mutant $1" "NOT DETECTED ($v)"; fail=1; fi
}
mutant "schedule() ignoring slots" HubSlots 1 \
  '/\ fresh[w] /\ Used(w) < Slots[w]' '/\ fresh[w]'
mutant "submit() not joining the active job" OneActivePerKey 1 \
  '/\ ~\E j \in JobIds : jobs[j].state \in Active /\ jobs[j].key = k' '/\ TRUE'
mutant "schedule() to a Mac listing the id" RunMatchesAttempt 2 \
  '    /\ j \notin Ids(w)
' ''
# With RunMatchesAttempt, worker_job()'s attempt guard changes nothing on its own: both must be removed.
mutant "worker_job()/schedule() without attempt" CacheFromCurrentAttempt 2 \
  'Owns(r, w) == Mine(r.id, w) /\ jobs[r.id].attempt = r.attempt' 'Owns(r, w) == Mine(r.id, w)' \
  '    /\ j \notin Ids(w)
' ''
mutant "used() without what the agent names" BuildSlots 1 \
  ' \cup listed[w])' ')'
mutant "heartbeat() not storing what it handed out" BuildSlots 1 \
  "listed' = [listed EXCEPT ![w] = S \cup out]" "listed' = [listed EXCEPT ![w] = S]"
mutant "OUT shared per key" NoFalseFailure 2 \
  'OutPath(r) == Tag(r)' 'OutPath(r) == KeyOf(r)'
mutant "schedule() without the source" SourceBeforeAssign 1 \
  '/\ jobs[j].state = "queued" /\ jobs[j].src
    /\ fresh[w]' '/\ jobs[j].state = "queued"
    /\ fresh[w]'

exit $fail
