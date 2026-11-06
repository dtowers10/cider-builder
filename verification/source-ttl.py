#!/usr/bin/env python3
"""SOURCE_TTL: the hub never cuts off an upload that is still going, and still cancels a job whose client is gone.

    verification/source-ttl.py              checks against bin/cider-build-hub; exits 0 if all pass
    verification/source-ttl.py --rev REV    the same against the hub at a git revision (main: the bug shows)

Runs a copy of the hub on 127.0.0.1 with its own CIDER_BUILD_HOME and SOURCE_TTL lowered to TTL seconds, so
every case takes seconds; recover() runs every 5 s. The cases run at the same time, each with its own job:
  - a whole-project upload that trickles in over ~3 TTL is accepted, not cancelled;
  - an incremental upload (manifest, then a delta that trickles in over ~3 TTL) is accepted, not cancelled;
  - a client that submits and never uploads loses its job;
  - a client that dies mid-upload (connection closed) loses its job;
  - a client that vanishes mid-upload (connection left open) is cut off with 408 and loses its job.
Does not touch the real hub or the Macs.
"""
import argparse
import gzip
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTL = 4
SLOW_S = 3 * TTL + 2       # how long the slow uploads take
GONE_S = TTL + 5 + 4       # a gone client's job is cancelled within this (TTL, one recover() round, slack)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(method, path, body=None):
    with urllib.request.urlopen(urllib.request.Request(base + path, data=body, method=method), timeout=30) as r:
        return r.read().decode()


def submit(proj, key):
    form = {"proj": proj, "key": key, "plat": "ios", "kind": "ios_native", "client": "ttl", "waiter": "ttl-" + key}
    what, job, need = call("POST", "/submit", urllib.parse.urlencode(form).encode()).split()[:3]
    assert what == "job" and need == "1", (what, job, need)
    return job


def state(job):  # without a waiter, so polling does not count as the client being alive
    return call("GET", "/poll?job=%s&offset=0" % job).split()[0]


def tar_gz(files):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:gz") as t:
        for nm, data in files.items():
            ti = tarfile.TarInfo(nm)
            ti.size, ti.mode = len(data), 0o644
            t.addfile(ti, io.BytesIO(data))
    return b.getvalue()


def open_put(path, length):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.putrequest("PUT", path)
    c.putheader("Content-Length", str(length))
    c.endheaders()
    return c


def slow_put(path, body, seconds):
    c = open_put(path, len(body))
    n = max(1, len(body) // seconds)
    for i in range(0, len(body), n):
        c.send(body[i:i + n])
        time.sleep(1)
    r = c.getresponse()
    return r.status, r.read().decode().strip()


def until_cancelled(job, since):
    while True:
        s, took = state(job), time.time() - since
        if s == "cancelled" or took > GONE_S:
            return "%s %.0f s after the client was last heard" % (s, took)
        time.sleep(0.5)


def slow_full():
    job = submit("ttl-full", "k1")
    r = slow_put("/source?job=" + job, tar_gz({"big.bin": os.urandom(14 << 10)}), SLOW_S)
    return r == (200, "queued") and state(job) == "queued", "PUT %s; poll %s" % (r, state(job))


def slow_delta():
    old, new = b"kept in the base", os.urandom(14 << 10)
    seed = submit("ttl-delta", "k0")
    call("PUT", "/source?job=" + seed, tar_gz({"old.txt": old}))
    job = submit("ttl-delta", "k1")
    def sha(b):
        return hashlib.sha256(b).hexdigest()
    manifest = gzip.compress(json.dumps([["old.txt", "f", 0o644, 0, sha(old)], ["new.bin", "f", 0o644, 0, sha(new)]]).encode())
    for _ in range(50):  # the base is seeded in the background after the first upload
        try:
            need = call("POST", "/source/manifest?job=" + job, manifest).split()
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            time.sleep(0.1)
    else:
        return False, "the hub never had a base tree for ttl-delta"
    if need != [sha(new)]:
        return False, "the hub asked for %r" % need
    r = slow_put("/source/delta?job=" + job, tar_gz({sha(new): new}), SLOW_S)
    return r == (200, "queued") and state(job) == "queued", "PUT %s; poll %s" % (r, state(job))


def never_uploads():
    job = submit("ttl-none", "k1")
    r = until_cancelled(job, time.time())
    return r.startswith("cancelled"), r


def dies_mid_upload():
    job = submit("ttl-dies", "k1")
    c = open_put("/source?job=" + job, 10000)
    c.send(b"x" * 100)
    c.close()
    r = until_cancelled(job, time.time())
    return r.startswith("cancelled"), r


def vanishes_mid_upload():
    job = submit("ttl-vanishes", "k1")
    c = open_put("/source?job=" + job, 10000)
    c.send(b"x" * 100)
    last = time.time()
    c.sock.settimeout(GONE_S)
    try:
        r = c.getresponse()
        reply = "%d after %.0f s" % (r.status, time.time() - last)
        cut = r.status == 408
    except OSError:
        reply, cut = "no reply in %d s" % GONE_S, False
    res = until_cancelled(job, last)
    return cut and res.startswith("cancelled"), "hub replied %s; %s" % (reply, res)


CASES = [
    ("a whole-project upload slower than 3 TTL is accepted", slow_full),
    ("an incremental upload whose delta is slower than 3 TTL is accepted", slow_delta),
    ("a client that never uploads loses its job", never_uploads),
    ("a client that dies mid-upload loses its job", dies_mid_upload),
    ("a client that vanishes mid-upload is cut off (408) and loses its job", vanishes_mid_upload),
]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--rev", help="run the hub from this git revision instead of the working tree")
args = ap.parse_args()

tmp = tempfile.mkdtemp(prefix="cider-build-ttl-")
home = os.path.join(tmp, "hub")
os.makedirs(os.path.join(home, "bin"))
code = (subprocess.check_output(["git", "-C", REPO, "show", "%s:bin/cider-build-hub" % args.rev]).decode() if args.rev
        else open(os.path.join(REPO, "bin", "cider-build-hub")).read())
code, n = re.subn(r"^SOURCE_TTL = \d+", "SOURCE_TTL = %d" % TTL, code, flags=re.M)
assert n == 1, "SOURCE_TTL not found in the hub"
hub_py = os.path.join(home, "bin", "cider-build-hub")
with open(hub_py, "w") as f:
    f.write(code)

port = free_port()
base = "http://127.0.0.1:%d" % port
proc = subprocess.Popen([sys.executable, hub_py], stderr=open(os.path.join(tmp, "hub.log"), "w"),
                        env=dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port),
                                 CIDER_BUILD_TAILNET_PORT=str(free_port()), PATH="/usr/bin:/bin"))
results = {}
try:
    for _ in range(100):
        try:
            call("GET", "/status")
            break
        except OSError:
            time.sleep(0.1)

    def run(what, f):
        try:
            results[what] = f()
        except Exception as e:  # noqa: BLE001 - reported as a failed case
            results[what] = (False, "unexpected error: %r" % e)

    threads = [threading.Thread(target=run, args=c) for c in CASES]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
finally:
    proc.terminate()
    proc.wait()

failures = 0
for what, _ in CASES:
    ok, detail = results[what]
    print("%s  %s: %s" % ("OK  " if ok else "FAIL", what, detail))
    failures += not ok
if failures:
    print("hub log and CIDER_BUILD_HOME in %s" % tmp)
else:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failures else 0)
