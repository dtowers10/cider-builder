#!/usr/bin/env python3
"""`cider-build warm` against the hub's SOURCE_TTL, with the real client and hub. Rule WarmStopsOnlyFromPanel.

    verification/warm-upload.py                  checks with SOURCE_TTL = 10 s (about 1 min); exits 0 if all pass
    verification/warm-upload.py --rev main       bin/ from that git revision
    verification/warm-upload.py --ttl 30         another SOURCE_TTL, written into the hub's copy

Every upload is throttled to last about 2.5 x SOURCE_TTL. No Mac takes the jobs, so a job that keeps its
source stays queued. The scenarios run at once, each with its own android_native project and proxy:
  full       a first warm-up (whole project) slower than the TTL: queued, and the hub keeps it
  delta      an incremental warm-up (manifest + delta) slower than the TTL: the same
  stalled    a warm job whose upload stops sending (connection left open): the hub still cleans it up
  crashed    a warm job whose client dies before uploading anything: the hub still cleans it up
  cancelled  the panel cancels while warm uploads: warm prints that, not "queued", and exits 1
Does not touch the real hub or the Macs.
"""
import argparse
import importlib.machinery
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = importlib.machinery.SourceFileLoader("source_delta", os.path.join(HERE, "source-delta.py")).load_module()

ap = argparse.ArgumentParser()
ap.add_argument("--rev")
ap.add_argument("--ttl", type=int, default=10)
a = ap.parse_args()
TTL = a.ttl

tmp = tempfile.mkdtemp(prefix="cider-build-warm-")
hub_home, fakebin, client_dir = (os.path.join(tmp, d) for d in ("hub", "fakebin", "client"))
for d in (os.path.join(hub_home, "bin"), fakebin, client_dir):
    os.makedirs(d)
with open(os.path.join(fakebin, "tailscale"), "w") as f:
    f.write("#!/bin/sh\nexit 1\n")
os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
hub_py = os.path.join(hub_home, "bin", "cider-build-hub")
D.install(a.rev, "cider-build-hub", hub_py)
with open(hub_py) as f:
    code, n = re.subn(r"^SOURCE_TTL = \d+", "SOURCE_TTL = %d" % TTL, f.read(), flags=re.M)
assert n == 1, "SOURCE_TTL not found in the hub"
with open(hub_py, "w") as f:
    f.write(code)
D.install(a.rev, "cider-build", os.path.join(client_dir, "cider-build"))
port = D.free_port()
hub = subprocess.Popen([sys.executable, os.path.join(hub_home, "bin", "cider-build-hub")],
                       env=dict(os.environ, CIDER_BUILD_HOME=hub_home, CIDER_BUILD_PORT=str(port),
                                CIDER_BUILD_TAILNET_PORT=str(D.free_port()), PATH=fakebin + ":/usr/bin:/bin"),
                       stderr=open(os.path.join(tmp, "hub.log"), "w"))
HUB = "http://127.0.0.1:%d" % port


def call(method, path, body=None):
    with urllib.request.urlopen(urllib.request.Request(HUB + path, data=body, method=method), timeout=30) as r:
        return r.read().decode()


def job(jid):
    return json.loads(call("GET", "/api/job?job=" + jid))["job"]


def warm(proj, rate):
    """Runs `cider-build warm android proj` through a proxy limited to `rate` bytes/s: (rc, stdout, stderr)."""
    proxy = D.Throttle(port, rate)
    env = dict(os.environ, CIDER_BUILD_HUB="http://127.0.0.1:%d" % proxy.port, HOME=client_dir,
               XDG_CACHE_HOME=os.path.join(tmp, "xdg"), CIDER_BUILD_FORCE="")
    p = subprocess.run(["bash", os.path.join(client_dir, "cider-build"), "warm", "android", proj], env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def slow(nbytes):
    return nbytes / (2.5 * TTL)


def job_id(out):
    return out.rsplit("(job ", 1)[-1].rstrip(")") if "(job " in out else ""


results = []
rlock = threading.Lock()


def check(name, ok, detail=""):
    with rlock:
        print("%-74s %-4s  %s" % (name, "OK" if ok else "FAIL", detail))
        results.append(ok)


def project(name, assets_mb):
    root = os.path.join(tmp, name)
    D.make_project(root, 20, assets_mb)
    return root


def full():
    proj = project("full", 4)
    t0 = time.time()
    rc, out, err = warm(proj, slow(4 << 20))
    took, jid = time.time() - t0, job_id(out)
    j = job(jid) if jid else {}
    check("full: the upload took longer than SOURCE_TTL", took > TTL + 5, "%.0f s, TTL %d s" % (took, TTL))
    check("full: warm prints queued and exits 0", rc == 0 and out == "android: queued (job %s)" % jid, "rc=%d %r" % (rc, out))
    check("full: the hub kept the job, with its source", j.get("state") == "queued" and j.get("src"),
          "%s src=%s" % (j.get("state"), j.get("src")))


def delta():
    proj = project("delta", 8)
    rc, out, _ = warm(proj, 0)  # unthrottled: seeds the base tree
    for _ in range(100):
        if os.path.isdir(os.path.join(hub_home, "bases", "delta-android")):
            break
        time.sleep(0.2)
    check("delta: the first warm-up seeded the base", rc == 0 and os.path.isdir(os.path.join(hub_home, "bases", "delta-android")), out)
    for n in (0, 1):  # two 2 MB assets change: a ~4 MB delta
        with open(os.path.join(proj, "assets", "img%02d" % n, "a%04d.png" % n), "wb") as f:
            f.write(os.urandom(2 << 20))
    t0 = time.time()
    rc, out, err = warm(proj, slow(4 << 20))
    took, jid = time.time() - t0, job_id(out)
    j = job(jid) if jid else {}
    check("delta: the upload was incremental and took longer than SOURCE_TTL",
          "Uploading the changes" in err and "whole project" not in err and took > TTL + 5, "%.0f s" % took)
    check("delta: warm prints queued and exits 0", rc == 0 and out == "android: queued (job %s)" % jid, "rc=%d %r" % (rc, out))
    check("delta: the hub kept the job, with its source", j.get("state") == "queued" and j.get("src") and j.get("src_via") == "delta",
          "%s src=%s via=%s" % (j.get("state"), j.get("src"), j.get("src_via")))


def submit_warm(key):
    form = urllib.parse.urlencode({"proj": "dead", "key": key, "plat": "android", "kind": "android_native"})
    return call("POST", "/submit", form.encode()).split()[1]


def wait_cancelled(jid, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if job(jid)["state"] == "cancelled":
            return time.time() - t0
        time.sleep(1)
    return None


def stalled():
    jid = submit_warm("stalled")
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(b"PUT /source?job=%s HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\n" % jid.encode() + os.urandom(50000))
    took = wait_cancelled(jid, TTL * 3 + 15)  # the connection stays open, silent
    s.close()
    check("stalled: a warm upload that stops sending is cleaned up", took is not None,
          "after %.0f s" % took if took else "still %s" % job(jid)["state"])


def crashed():
    jid = submit_warm("crashed")
    took = wait_cancelled(jid, TTL * 3 + 15)
    check("crashed: a warm job that never gets a byte is cleaned up", took is not None,
          "after %.0f s" % took if took else "still %s" % job(jid)["state"])


def cancelled():
    proj = project("cancelled", 4)
    res = {}
    t = threading.Thread(target=lambda: res.update(r=warm(proj, slow(4 << 20))))
    t.start()
    jid = None
    for _ in range(300):
        act = [x for x in json.loads(call("GET", "/api/state"))["active"] if x["proj"] == "cancelled"]
        if act:
            jid = act[0]["id"]
            break
        time.sleep(0.1)
    time.sleep(2)
    call("POST", "/detach?job=%s&all=1" % jid)
    t.join()
    rc, out, _ = res["r"]
    check("cancelled: warm says the panel cancelled it, and exits 1",
          rc == 1 and out == "android: cancelled on the hub (job %s)" % jid, "rc=%d %r" % (rc, out))


try:
    for _ in range(100):
        try:
            call("GET", "/status")
            break
        except OSError:
            time.sleep(0.1)
    print("SOURCE_TTL %d s, bin/ from %s" % (TTL, a.rev or "working copy"))
    ts = [threading.Thread(target=f) for f in (full, delta, stalled, crashed, cancelled)]
    [t.start() for t in ts]
    [t.join() for t in ts]
finally:
    hub.terminate()
    hub.wait()
    print("Test directory: %s" % tmp)
sys.exit(0 if len(results) == 10 and all(results) else 1)  # a scenario that crashed checks nothing
