#!/usr/bin/env python3
"""Summarizes a TLC counterexample: for each step, the action and only the variables that change."""
import re
import sys

text = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
states = re.split(r"\n(?=State \d+: )", text)
prev = {}
for block in states:
    m = re.match(r"State (\d+): <(\w+)(?: line (\d+), col \d+ to line \d+, col \d+ of module (\w+))?", block)
    if not m:
        continue
    cur = {}
    for v in re.finditer(r"^/\\ (\w+) = (.*?)(?=^/\\ |\Z)", block, re.S | re.M):
        cur[v.group(1)] = " ".join(v.group(2).split())
    where = " (%s:%s)" % (m.group(4), m.group(3)) if m.group(3) else ""
    print("%s. %s%s" % (m.group(1), m.group(2), where))
    for k, val in cur.items():
        if prev.get(k) != val and prev:
            print("     %s = %s" % (k, val))
    prev = cur
