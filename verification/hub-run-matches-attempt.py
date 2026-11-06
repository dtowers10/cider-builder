#!/usr/bin/env python3
"""Reproduces RunMatchesAttempt against a real hub, without touching the fleet.

Starts bin/cider-build-hub on 127.0.0.1 with a temporary CIDER_BUILD_HOME and a free port, with BEAT_TTL and
LOST_TTL cut to 2 s and 3 s in this process only (a partition longer than 60 s expires both), without
listening on the tailnet or running a drain command. Simulates the agent over HTTP: receives the job, stops
sending heartbeats until recover() puts it back in the queue, sends heartbeats again with the old id in
`running`, and checks that the next attempt reaches an agent that builds it.
Exits 0 if the hub behaves correctly.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "cider-build-hub")
LABEL = "mac-test-01"
BEAT_TTL, LOST_TTL = 2, 3

LOADER = """
import importlib.machinery, importlib.util, sys
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("hub", sys.argv[1])
hub = importlib.util.module_from_spec(importlib.util.spec_from_loader("hub", loader))
loader.exec_module(hub)
hub.BEAT_TTL, hub.LOST_TTL = int(sys.argv[2]), int(sys.argv[3])
hub.listen_tailnet = lambda: None
hub.refresh_drained = lambda: None
hub.main()
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(method, path, body=None):
    req = urllib.request.Request(base + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def beat(running):
    body = {"label": LABEL, "boot": "boot1", "user": "test", "ram_gb": 32, "free_gb": 20, "running": running,
            "tools_ready": True, "xcode": "16.0", "version": "3", "info": {}}
    return json.loads(call("POST", "/w/heartbeat", json.dumps(body).encode()))


def job(jid):
    return json.loads(call("GET", "/api/job?job=" + jid))["job"]


failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


home = tempfile.mkdtemp(prefix="cider-build-test-")
port = free_port()
base = "http://127.0.0.1:%d" % port
env = dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port), CIDER_BUILD_TAILNET_PORT=str(free_port()),
           CIDER_BUILD_UPDATE_CHECK_S="0")
hub = subprocess.Popen([sys.executable, "-c", LOADER, HUB, str(BEAT_TTL), str(LOST_TTL)], env=env,
                       stderr=open(os.path.join(home, "hub.err"), "w"))
try:
    for _ in range(50):
        try:
            call("GET", "/status")
            break
        except OSError:
            time.sleep(0.1)
    call("PUT", "/workers/%s?slots=1&ram=32" % LABEL)
    beat([])
    jid = call("POST", "/submit", b"proj=test&key=k1&plat=ios&kind=expo&waiter=cli1").split()[1]
    call("PUT", "/source?job=" + jid, b"source")

    got = beat([])["jobs"]
    check([(j["id"], j["attempt"]) for j in got] == [(jid, 1)], "the agent receives attempt 1")

    deadline = time.time() + LOST_TTL + 10
    while job(jid)["state"] != "queued" and time.time() < deadline:
        time.sleep(0.5)
    j = job(jid)
    check(j["state"] == "queued" and j["retries"] == 1, "after LOST_TTL without heartbeats, recover() puts it back in the queue")

    r = beat([jid])
    j = job(jid)
    print("      heartbeat with the old id: response %s, job %s attempt %d on %s"
          % (json.dumps(r), j["state"], j["attempt"], j["worker"]))
    check(jid in r["cancel"], "the hub orders the old Run cancelled")

    r = beat([jid])
    j = job(jid)
    print("      heartbeat with the old Run still dying: response %s, job %s attempt %d"
          % (json.dumps(r), j["state"], j["attempt"]))
    check(j["state"] != "building", "the hub does not mark building an attempt the agent does not have")

    r = beat([])
    j = job(jid)
    print("      heartbeat without the old Run: response %s, job %s attempt %d"
          % (json.dumps([(x["id"], x["attempt"]) for x in r["jobs"]]), j["state"], j["attempt"]))
    check([(x["id"], x["attempt"]) for x in r["jobs"]] == [(jid, j["attempt"])] and j["attempt"] == 2,
          "once the old Run dies, the agent receives attempt 2")

    beat([jid])
    q = "job=%s&attempt=2&label=%s&rc=0" % (jid, LABEL)
    artifact = b"artifact"
    req = urllib.request.Request(base + "/w/result?" + q, data=artifact, method="POST",
                                 headers={"Content-Length": str(len(artifact)), "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        res = "HTTP %d" % e.code
    check(res == "done", "attempt 2 delivers its result and the job ends done (%s)" % res)
finally:
    hub.terminate()
    hub.wait()

print("temporary hub at %s, CIDER_BUILD_HOME=%s" % (base, home))
sys.exit(1 if failures else 0)
