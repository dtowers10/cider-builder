#!/usr/bin/env python3
"""Another developer's Ctrl-C never cancels the build you are still waiting for (MacBuild.tla, CtrlCOnlyStopsYours).

    verification/waiter-ttl.py              checks (about 2.5 min); exits 0 if all pass
    verification/waiter-ttl.py --rev REV    bin/cider-build from that git revision (e.g. main, for the baseline)

The hub stops counting a waiter WAITER_TTL s after its last poll, and then the last remaining client's Ctrl-C
cancels the build. So the client has to give up waiting before the hub forgets it. The scenario: developer A
runs the real bin/cider-build against a hub on 127.0.0.1 with no Macs, through a proxy. Once A's upload is in
and A is polling, the proxy refuses A for longer than WAITER_TTL. Then developer B joins the same job directly
and presses Ctrl-C (detach), and the proxy lets A through again. A must not report the build as cancelled: by
then A has given up. B's Ctrl-C must still cancel, because a client that is gone stops counting.
Does not touch the real hub or the Macs.
"""
import argparse
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

sys.stdout.reconfigure(line_buffering=True)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def source(rev, name):
    if rev:
        return subprocess.check_output(["git", "-C", REPO, "show", "%s:bin/%s" % (rev, name)]).decode()
    with open(os.path.join(REPO, "bin", name)) as f:
        return f.read()


class Gate:
    """TCP proxy in front of the hub. While closed, it accepts each connection and drops it right away."""

    def __init__(self, target_port):
        self.target, self.open = target_port, True
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(64)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            c, _ = self.srv.accept()
            if not self.open:
                c.close()
                continue
            u = socket.create_connection(("127.0.0.1", self.target))
            threading.Thread(target=self.pump, args=(c, u), daemon=True).start()
            threading.Thread(target=self.pump, args=(u, c), daemon=True).start()

    @staticmethod
    def pump(a, b):
        try:
            while True:
                data = a.recv(64 * 1024)
                if not data:
                    break
                b.sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev")
    a = ap.parse_args()

    client_src, hub_src = source(a.rev, "cider-build"), source(None, "cider-build-hub")
    ttl = int(re.search(r"^WAITER_TTL = (\d+)", hub_src, re.M).group(1))
    m = re.search(r"^PATIENCE=(\d+) POLL_MAX=(\d+)$", client_src, re.M)
    # The client checks the time only after a failed poll; then it may sleep 2 s and try one more poll.
    worst = int(m.group(1)) + 2 + int(m.group(2)) if m else None
    check(worst is not None and worst < ttl,
          "the client stops waiting (worst case %s s) before the hub forgets it (WAITER_TTL %d s)" % (worst, ttl))

    tmp = tempfile.mkdtemp(prefix="cider-build-waiter-")
    hub_home, fakebin, home, proj = (os.path.join(tmp, d) for d in ("hub", "fakebin", "home", "MyApp"))
    for d in (os.path.join(hub_home, "bin"), fakebin, home, os.path.join(proj, "MyApp.xcodeproj")):
        os.makedirs(d)
    with open(os.path.join(fakebin, "tailscale"), "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
    with open(os.path.join(proj, "main.swift"), "w") as f:
        f.write('print("hello")\n')
    client = os.path.join(tmp, "cider-build")
    with open(client, "w") as f:
        f.write(client_src)
    os.chmod(client, 0o755)

    port = free_port()
    base = "http://127.0.0.1:%d" % port
    hub = subprocess.Popen([sys.executable, os.path.join(REPO, "bin", "cider-build-hub")],
                           env=dict(os.environ, CIDER_BUILD_HOME=hub_home, CIDER_BUILD_PORT=str(port),
                                    CIDER_BUILD_TAILNET_PORT=str(free_port()), PATH=fakebin + ":/usr/bin:/bin"),
                           stderr=open(os.path.join(tmp, "hub.log"), "w"))
    gate = Gate(port)

    def call(method, path, **q):
        req = urllib.request.Request(base + path, data=urllib.parse.urlencode(q).encode() if method == "POST" else None,
                                     method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode()

    log = open(os.path.join(tmp, "client-A.log"), "w+")
    A = None
    try:
        for _ in range(100):
            try:
                call("GET", "/status")
                break
            except OSError:
                time.sleep(0.1)
        A = subprocess.Popen([client, "ios", proj], stdout=log, stderr=subprocess.STDOUT,
                             env=dict(os.environ, HOME=home, XDG_CACHE_HOME=os.path.join(home, ".cache"),
                                      CIDER_BUILD_HUB="http://127.0.0.1:%d" % gate.port))
        job = None
        for _ in range(300):  # until A's source is in and A has polled at least once
            # <id>.json only: the client's manifest attempt leaves <id>.manifest.json there too
            files = [f for f in os.listdir(os.path.join(hub_home, "jobs")) if f.endswith(".json") and f.count(".") == 1]
            if files:
                with open(os.path.join(hub_home, "jobs", files[0])) as f:
                    job = json.load(f)
                if job["src"] and job["waiters"] and max(job["waiters"].values()) > job["created"]:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError("A never started waiting")
        check(A.poll() is None, "A uploads the source and waits for build %s" % job["id"])

        gate.open = False
        t0 = time.time()
        print("      the hub stops hearing A; B joins and presses Ctrl-C after %d s…" % (ttl + 5))
        exited = None
        while time.time() - t0 < ttl + 5:
            if exited is None and A.poll() is not None:
                exited = time.time() - t0
            time.sleep(0.5)
        # B: the same version, waiting, then Ctrl-C (the INT trap calls detach)
        b = call("POST", "/submit", proj=job["proj"], key=job["key"], plat="ios", kind=job["kind"],
                 client="devB", waiter="devB").split()
        check(b[:2] == ["job", job["id"]], "B joins A's build")
        detach = call("POST", "/detach?" + urllib.parse.urlencode({"job": job["id"], "waiter": "devB"})).strip()
        gate.open = True
        try:
            A.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        log.seek(0)
        out = log.read()
        check("cancelled on the hub" not in out, "A never reports the build as cancelled by B's Ctrl-C")
        check(exited is not None and exited < ttl,
              "A stops waiting before the hub forgets it (after %s s without the hub)" %
              ("%.0f" % exited if exited is not None else "more than %d" % (ttl + 5)))
        check(detach == "cancelled", "B's Ctrl-C cancels once A is gone (detach answered %r)" % detach)
        print("      A's last lines: %s" % " | ".join(out.strip().splitlines()[-2:]))
    except (OSError, ValueError, KeyError, IndexError, RuntimeError) as e:
        check(False, "unexpected error: %r" % e)
    finally:
        if A and A.poll() is None:
            A.kill()
        hub.terminate()
        hub.wait()
    print("hub log, client log and CIDER_BUILD_HOME in %s" % tmp)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
