#!/usr/bin/env python3
"""Reproduces the NoFalseFailure counterexample locally with the real hub, agent and build.sh.

    verification/run-order.py          with bin/ from the working copy
    verification/run-order.py <rev>    with bin/ from that git revision

Everything runs in a temporary directory: a hub on 127.0.0.1 with its own CIDER_BUILD_HOME, a fake agent
(its own HOME, no main()) and an android_native project whose gradlew only writes an .apk.
Does not touch the real hub or the Macs. Exits 0 if all checks pass.
"""
import importlib.machinery
import io
import json
import os
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(line_buffering=True)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REV = sys.argv[1] if len(sys.argv) > 1 else None
LABEL = "mac-test-01"
GRADLEW = """#!/bin/bash
mkdir -p app/build/outputs/apk/debug
echo "apk from $STAGE" > app/build/outputs/apk/debug/app-debug.apk
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def install(name, dest):
    data = (subprocess.check_output(["git", "-C", REPO, "show", "%s:bin/%s" % (REV, name)]) if REV
            else open(os.path.join(REPO, "bin", name), "rb").read())
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, 0o755)


def source_tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("gradlew")
        info.size, info.mode = len(GRADLEW), 0o755
        t.addfile(info, io.BytesIO(GRADLEW.encode()))
    return buf.getvalue()


tmp = tempfile.mkdtemp(prefix="cider-build-order-")
home, hub_home, fakebin = (os.path.join(tmp, d) for d in ("home", "hub", "fakebin"))
for d in (os.path.join(home, "cider-build"), os.path.join(hub_home, "bin"), fakebin):
    os.makedirs(d)
with open(os.path.join(fakebin, "tailscale"), "w") as f:
    f.write("#!/bin/sh\nexit 1\n")  # the test hub does not listen on the tailnet
os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
install("cider-build-hub", os.path.join(hub_home, "bin", "cider-build-hub"))
install("cider-build-worker", os.path.join(home, "cider-build", "cider-build-worker"))
install("build.sh", os.path.join(home, "cider-build", "build.sh"))

port = free_port()
HUB = "http://127.0.0.1:%d" % port
hub = subprocess.Popen([sys.executable, os.path.join(hub_home, "bin", "cider-build-hub")],
                       env=dict(os.environ, CIDER_BUILD_HOME=hub_home, CIDER_BUILD_PORT=str(port),
                                CIDER_BUILD_TAILNET_PORT=str(free_port()), CIDER_BUILD_UPDATE_CHECK_S="0",
                                PATH=fakebin + ":/usr/bin:/bin"),
                       stderr=open(os.path.join(tmp, "hub.log"), "w"))
with open(os.path.join(home, "cider-build", "worker.json"), "w") as f:
    json.dump({"label": LABEL, "hub": HUB}, f)
os.environ["HOME"] = home
W = importlib.machinery.SourceFileLoader("worker", os.path.join(home, "cider-build", "cider-build-worker")).load_module()
W.reap()

for _ in range(50):
    try:
        W.http("PUT", "/workers/%s?slots=2" % LABEL, b"")
        break
    except OSError:
        time.sleep(0.1)


def beat():
    """The body of main()'s loop, without Machine (sysctl and memory_pressure are macOS-only)."""
    with W.lock:
        ids = list(W.running)
    body = {"label": LABEL, "boot": W.BOOT, "user": "test", "ram_gb": 32, "free_gb": 16, "running": ids,
            "tools_ready": True, "xcode": "16.0", "version": W.VERSION, "info": {}}
    resp = json.loads(W.http("POST", "/w/heartbeat", json.dumps(body).encode()))
    new = []
    with W.lock:
        for jid in resp.get("cancel", []):
            if jid in W.running:
                W.running[jid].cancel("the hub asked for it")
        for job in resp.get("jobs", []):
            if job["id"] not in W.running:
                new.append(W.running.setdefault(job["id"], W.Run(job)))
    return new


def submit(waiter):
    form = urllib.parse.urlencode({"proj": "app", "key": "v1", "plat": "android", "kind": "android_native",
                                   "waiter": waiter, "client": "test"}).encode()
    reply = W.http("POST", "/submit", form).decode().split()
    if reply[0] == "cached":
        return None
    W.http("PUT", "/source?job=" + reply[1], source_tarball())
    return reply[1]


def job(jid):
    return json.loads(W.http("GET", "/api/job?job=" + jid))["job"]


def cached():
    path = os.path.join(hub_home, "cache", "app", "v1-android.apk")
    return open(path, "rb").read() if os.path.isfile(path) else None


def check(name, ok, detail):
    print("%-58s %-4s  %s" % (name, "OK" if ok else "FAIL", detail))
    return ok


results = []
try:
    a = submit("client-1")
    [run_a] = beat()
    W.http("POST", "/detach?job=%s&waiter=client-1" % a, b"")
    b = submit("client-2")
    [run_b] = beat()
    assert run_a.cancelled, "the heartbeat did not cancel the old Run"

    report = W.Run.report

    def report_after_old_cleanup(self, rc, out):
        if self is run_b:
            print("the new Run's build.sh finished with rc=%d; in ~/builds/out: %s"
                  % (rc, sorted(os.listdir(W.OUT))))
            run_a.run()
            print("the old Run went through its finally; in ~/builds/out: %s" % sorted(os.listdir(W.OUT)))
        return report(self, rc, out)

    W.Run.report = report_after_old_cleanup
    run_b.run()
    W.Run.report = report
    jb = job(b)
    results.append(check("Ctrl-C and relaunch: the new Run delivers its build",
                         jb["state"] == "done" and jb["rc"] == 0, "state=%s rc=%s" % (jb["state"], jb["rc"])))
    art = cached()
    results.append(check("The hub cache has the new Run's .apk",
                         art is not None and art.startswith(b"apk from "), repr(art)))
    results.append(check("The agent leaves nothing in ~/builds/out", os.listdir(W.OUT) == [], str(os.listdir(W.OUT))))
    if art is not None:
        results.append(check("Another request for the same version comes from the cache", submit("client-3") is None, ""))
finally:
    hub.terminate()
    hub.wait()
    print("Test directory: %s" % tmp)
sys.exit(0 if results and all(results) else 1)
