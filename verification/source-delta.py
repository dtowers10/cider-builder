#!/usr/bin/env python3
"""Incremental source upload, end to end, with the real client, hub, agent and build.sh.

    verification/source-delta.py                     checks (small project, no throttling); exits 0 if all pass
    verification/source-delta.py --measure           timings only, for a bigger project behind a throttled link
        [--files N] [--assets-mb M] [--rate-mbit R]  project size and client -> hub bandwidth
        [--rev REV]                                  bin/ from that git revision (e.g. main, for the baseline)
    verification/source-delta.py --hub-rev main      this client against an older hub: it falls back to the full upload

Everything runs in a temporary directory: a hub on 127.0.0.1 with its own CIDER_BUILD_HOME, an agent in this
process (its own HOME, the loop of main() without Machine), and bin/cider-build run as a subprocess against a
throttling proxy in front of the hub. The project is android_native; its gradlew writes, as the .apk, a digest
of the tree build.sh built from ($PWD after the rsync) and of the unpacked tarball ($STAGE): every path with its
type, mode, mtime and sha256. Does not touch the real hub or the Macs.
"""
import argparse
import hashlib
import importlib.machinery
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.stdout.reconfigure(line_buffering=True)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL = "mac-delta-01"
DIGEST = r'''
import hashlib, json, os, stat, sys
SKIP = {"build", ".gradle", ".idea", ".cxx", "local.properties", ".git", "node_modules"}
def digest(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP)
        for n in [None] + sorted(dirs + [f for f in files if f not in SKIP]):
            p = d if n is None else os.path.join(d, n)
            if n is not None and os.path.isdir(p) and not os.path.islink(p):
                continue  # listed when walked
            st = os.lstat(p)
            rel = os.path.relpath(p, root)
            if stat.S_ISLNK(st.st_mode):
                out.append([rel, "l", os.readlink(p)])
            elif stat.S_ISDIR(st.st_mode):
                out.append([rel, "d", oct(st.st_mode & 0o7777), int(st.st_mtime)])
            else:
                out.append([rel, "f", oct(st.st_mode & 0o7777), int(st.st_mtime), hashlib.sha256(open(p, "rb").read()).hexdigest()])
    return out
if __name__ == "__main__":
    print(json.dumps({"src": digest(sys.argv[1]), "stage": digest(sys.argv[2])}))
'''
GRADLEW = """#!/bin/bash
mkdir -p app/build/outputs/apk/debug
python3 "$(dirname "$0")/.digest.py" "$PWD" "$STAGE" > app/build/outputs/apk/debug/app-debug.apk
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def install(rev, name, dest):
    data = (subprocess.check_output(["git", "-C", REPO, "show", "%s:bin/%s" % (rev, name)]) if rev
            else open(os.path.join(REPO, "bin", name), "rb").read())
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, 0o755)


class Throttle:
    """TCP proxy in front of the hub. Client -> hub bytes are limited to `rate` bytes/s (0: unlimited) and counted."""

    def __init__(self, target_port, rate):
        self.target, self.rate, self.up = target_port, rate, 0
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(64)
        self.port = self.srv.getsockname()[1]
        self.lock = threading.Lock()
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            c, _ = self.srv.accept()
            u = socket.create_connection(("127.0.0.1", self.target))
            threading.Thread(target=self.pump, args=(c, u, True), daemon=True).start()
            threading.Thread(target=self.pump, args=(u, c, False), daemon=True).start()

    def pump(self, a, b, upstream):
        t0, sent = time.time(), 0
        try:
            while True:
                data = a.recv(64 * 1024)
                if not data:
                    break
                if upstream:
                    with self.lock:
                        self.up += len(data)
                    sent += len(data)
                    if self.rate:
                        ahead = sent / self.rate - (time.time() - t0)
                        if ahead > 0:
                            time.sleep(ahead)
                b.sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


def make_project(root, files, assets_mb, seed=7):
    """An android_native project: gradlew, `files` source files (text, ~8 KB each) and `assets_mb` MB of
    incompressible assets in 2 MB files, plus an empty folder, a symlink and excluded folders."""
    rnd = random.Random(seed)
    words = ["val", "fun", "class", "return", "if", "else", "import", "data", "override", "private", "String",
             "Int", "List", "map", "filter", "when", "object", "companion", "suspend", "launch"] + \
            ["ident%d" % i for i in range(400)]
    os.makedirs(root)
    with open(os.path.join(root, "gradlew"), "w") as f:
        f.write(GRADLEW)
    os.chmod(os.path.join(root, "gradlew"), 0o755)
    with open(os.path.join(root, ".digest.py"), "w") as f:
        f.write(DIGEST)
    with open(os.path.join(root, "settings.gradle"), "w") as f:
        f.write("include ':app'\n")
    for i in range(files):
        d = os.path.join(root, "modules", "m%02d" % (i % 40), "src", "main", "kotlin", "p%d" % (i % 7))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "F%05d.kt" % i), "w") as f:
            f.write("\n".join(" ".join(rnd.choice(words) for _ in range(12)) for _ in range(110)) + "\n")
    left, n = assets_mb << 20, 0
    while left > 0:
        d = os.path.join(root, "assets", "img%02d" % (n % 10))
        os.makedirs(d, exist_ok=True)
        size = min(left, 2 << 20)
        with open(os.path.join(d, "a%04d.png" % n), "wb") as f:
            f.write(rnd.randbytes(size))
        left -= size
        n += 1
    os.makedirs(os.path.join(root, "empty-dir"))
    os.symlink("settings.gradle", os.path.join(root, "settings.link"))
    for d in ("build", "app/build", ".gradle"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
        with open(os.path.join(root, d, "junk.bin"), "wb") as f:
            f.write(b"excluded" * 1000)


def tree_size(root):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(root) for f in fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--files", type=int)
    ap.add_argument("--assets-mb", type=int)
    ap.add_argument("--rate-mbit", type=float)
    ap.add_argument("--rev")
    ap.add_argument("--hub-rev")
    a = ap.parse_args()
    files = a.files if a.files is not None else (3000 if a.measure else 300)
    assets = a.assets_mb if a.assets_mb is not None else (200 if a.measure else 8)
    rate = (a.rate_mbit if a.rate_mbit is not None else (100 if a.measure else 0)) * 1e6 / 8

    tmp = tempfile.mkdtemp(prefix="cider-build-delta-")
    home, hub_home, fakebin = (os.path.join(tmp, d) for d in ("home", "hub", "fakebin"))
    for d in (os.path.join(home, "cider-build"), os.path.join(hub_home, "bin"), fakebin, os.path.join(tmp, "client")):
        os.makedirs(d)
    with open(os.path.join(fakebin, "tailscale"), "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
    install(a.hub_rev or a.rev, "cider-build-hub", os.path.join(hub_home, "bin", "cider-build-hub"))
    install(a.rev, "cider-build-worker", os.path.join(home, "cider-build", "cider-build-worker"))
    install(a.rev, "build.sh", os.path.join(home, "cider-build", "build.sh"))
    install(a.rev, "cider-build", os.path.join(tmp, "client", "cider-build"))

    port = free_port()
    hub = subprocess.Popen([sys.executable, os.path.join(hub_home, "bin", "cider-build-hub")],
                           env=dict(os.environ, CIDER_BUILD_HOME=hub_home, CIDER_BUILD_PORT=str(port),
                                    CIDER_BUILD_TAILNET_PORT=str(free_port()), PATH=fakebin + ":/usr/bin:/bin"),
                           stderr=open(os.path.join(tmp, "hub.log"), "w"))
    proxy = Throttle(port, rate)
    with open(os.path.join(home, "cider-build", "worker.json"), "w") as f:
        json.dump({"label": LABEL, "hub": "http://127.0.0.1:%d" % port}, f)
    os.environ["HOME"] = home
    W = importlib.machinery.SourceFileLoader("worker", os.path.join(home, "cider-build", "cider-build-worker")).load_module()
    W.reap()
    for _ in range(50):
        try:
            W.http("PUT", "/workers/%s?slots=2" % LABEL, b"")
            break
        except OSError:
            time.sleep(0.1)

    stop = threading.Event()

    def agent():
        """The loop of main(), without Machine (sysctl and memory_pressure are macOS-only)."""
        while not stop.is_set():
            with W.lock:
                ids = list(W.running)
            body = {"label": LABEL, "boot": W.BOOT, "user": "test", "ram_gb": 32, "free_gb": 16, "running": ids,
                    "tools_ready": True, "xcode": "16.0", "version": W.VERSION, "info": {}}
            try:
                resp = json.loads(W.http("POST", "/w/heartbeat", json.dumps(body).encode(), timeout=15))
            except Exception:
                time.sleep(0.5)
                continue
            with W.lock:
                for jid in resp.get("cancel", []):
                    if jid in W.running:
                        W.running[jid].cancel("the hub asked for it")
                for job in resp.get("jobs", []):
                    if job["id"] not in W.running:
                        r = W.running[job["id"]] = W.Run(job)
                        threading.Thread(target=r.run, daemon=True).start()
            time.sleep(0.5)

    threading.Thread(target=agent, daemon=True).start()

    proj = os.path.join(tmp, "app")
    make_project(proj, files, assets)
    print("Project: %d source files + %d MB of assets, %.0f MB on disk (without excluded folders: see digest)."
          % (files, assets, tree_size(proj) / 1e6))
    print("Client -> hub link: %s" % ("%.0f Mbit/s" % (rate * 8 / 1e6) if rate else "unthrottled"))
    print("bin/ from: %s" % (a.rev or "working copy"))

    def hub_get(path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=30) as r:
            return r.read()

    def client(force=False):
        """Runs bin/cider-build android; returns the timeline, the job and the artifact's digest."""
        up0 = proxy.up
        env = dict(os.environ, CIDER_BUILD_HUB="http://127.0.0.1:%d" % proxy.port, XDG_CACHE_HOME=os.path.join(tmp, "xdg"),
                   HOME=os.path.join(tmp, "client"), CIDER_BUILD_FORCE="1" if force else "")
        t0 = time.time()
        p = subprocess.Popen(["bash", os.path.join(tmp, "client", "cider-build"), "android", proj], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = [(time.time() - t0, l.rstrip("\n")) for l in p.stderr]
        out = p.stdout.read().strip().splitlines()
        rc = p.wait()
        total = time.time() - t0
        hist = json.loads(hub_get("/api/history"))["jobs"]
        j = json.loads(hub_get("/api/job?job=" + hist[0]["id"]))["job"] if hist else {}
        apk = out[-1] if out else ""
        dig = json.load(open(apk)) if rc == 0 and os.path.isfile(apk) else None
        # From the hub's own timestamps: created (submit) -> src_at (whole source on the hub; this branch) and
        # created -> started (handed to the idle Mac: source + at most one 0.5 s heartbeat; also on main).
        src_s = j["src_at"] - j["created"] if j.get("src_at") else None
        wait_s = j["started"] - j["created"] if j.get("started") else None
        r = {"rc": rc, "total": total, "lines": lines, "job": j, "digest": dig, "up_bytes": proxy.up - up0,
             "src_s": src_s, "wait_s": wait_s}
        for t, l in lines:
            print("    %6.2fs  %s" % (t, l))
        print("    -> rc=%d, %.2f s total, created->src_at %s, created->started %s, %.2f MB client->hub, build %s"
              % (rc, total, "%.2f s" % src_s if src_s is not None else "-", "%.2f s" % wait_s if wait_s else "-",
                 r["up_bytes"] / 1e6,
                 "%.2f s" % ((j.get("finished") or 0) - (j.get("started") or 0)) if j.get("started") else "?"))
        return r

    def touch_one(i, text):
        p = os.path.join(proj, "modules", "m%02d" % (i % 40), "src", "main", "kotlin", "p%d" % (i % 7), "F%05d.kt" % i)
        with open(p, "a") as f:
            f.write(text)
        t = time.time() - 1000 - i  # a different mtime than before, which the tree must also carry
        os.utime(p, (t, t))

    def truth():
        """The digest of the client's own tree: what a correct upload must reproduce on the Mac."""
        out =subprocess.check_output([sys.executable, os.path.join(proj, ".digest.py"), proj, proj], text=True)
        return json.loads(out)["src"]

    results = []

    def same_tree(r):
        """(ok, detail): the agent unpacked ($STAGE) exactly the client's tree: paths, types, modes, mtimes, contents.
        ($PWD of build.sh is not compared with the client: building creates app/build/ there and changes app/'s mtime.)"""
        if not r["digest"]:
            return False, "no artifact"
        want, got = {e[0]: e for e in truth()}, {e[0]: e for e in r["digest"]["stage"]}
        diff = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
        return not diff, "%d entries" % len(got) if not diff else "differs: %s" % [(want.get(k), got.get(k)) for k in diff[:3]]

    def check(name, ok, detail=""):
        print("%-66s %-4s  %s" % (name, "OK" if ok else "FAIL", detail))
        results.append(ok)

    try:
        print("\n1. First build: the hub has no base tree for app-android")
        r1 = client()
        if a.hub_rev:
            touch_one(1, "// change 1\n")
            r2 = client()
            check("Older hub (%s): the client falls back to the full upload, both builds" % a.hub_rev,
                  r1["rc"] == 0 and r2["rc"] == 0 and r2["up_bytes"] > 1e6
                  and any("No incremental upload" in l for _, l in r2["lines"]), "%d bytes" % r2["up_bytes"])
            check("Older hub: the agent unpacked exactly the client's tree", *same_tree(r2))
            return 0 if all(results) else 1
        if a.measure:
            print("\n2. One source file changed")
            touch_one(1, "// change 1\n")
            r2 = client()
            print("\n3. One 2 MB asset changed")
            with open(os.path.join(proj, "assets", "img00", "a0000.png"), "r+b") as f:
                f.write(os.urandom(4096))
            r3 = client()
            print("\nSUMMARY (created->started, MB client->hub, build started->finished)")
            for n, r in (("first", r1), ("one file", r2), ("one asset", r3)):
                j = r["job"]
                print("  %-10s %6.2f s  %7.2f MB  build %.2f s  via=%s" % (n, r["wait_s"] or -1, r["up_bytes"] / 1e6,
                      j["finished"] - j["started"], j.get("src_via", "full (main)")))
            return 0
        check("1st build without a base: full upload, built", r1["rc"] == 0 and r1["job"].get("src_via") == "full",
              "src_via=%s, %d bytes" % (r1["job"].get("src_via"), r1["job"].get("src_bytes") or 0))
        check("1st build: the agent unpacked exactly the client's tree", *same_tree(r1))
        check("1st build: logs the fallback", any("No incremental upload" in l for _, l in r1["lines"]))

        print("\n2. One file changed")
        touch_one(1, "// change 1\n")
        r2 = client()
        check("2nd build after a one-file change: incremental upload",
              r2["rc"] == 0 and r2["job"].get("src_via") == "delta", "src_via=%s" % r2["job"].get("src_via"))
        check("2nd build: far fewer bytes from the client",
              r2["up_bytes"] * 20 < r1["up_bytes"], "%d vs %d bytes" % (r2["up_bytes"], r1["up_bytes"]))
        check("2nd build: the agent unpacked exactly the client's tree", *same_tree(r2))

        print("\n3. Same version again, forced: full upload of the same tree")
        r3 = client(force=True)
        check("Forced build of the same version: full upload", r3["rc"] == 0 and r3["job"].get("src_via") == "full")
        check("Delta and full upload: identical unpacked tarball ($STAGE)",
              r2["digest"] and r3["digest"] and r2["digest"]["stage"] == r3["digest"]["stage"],
              "%d entries" % len(r3["digest"]["stage"]) if r3["digest"] else "")
        check("Delta and full upload: identical tree for build.sh",
              r2["digest"] and r3["digest"] and r2["digest"]["src"] == r3["digest"]["src"])

        print("\n4. A corrupt base: one blob of the hub's base tree is overwritten, then one file changes")
        base = os.path.join(hub_home, "bases", "app-android")
        blob = sorted(os.listdir(base))[0]
        with open(os.path.join(base, blob), "r+b") as f:
            f.write(b"corrupt")
        touch_one(2, "// change 2\n")
        r4 = client()
        check("Corrupt base: the hub refuses the delta and the client falls back",
              r4["rc"] == 0 and r4["job"].get("src_via") == "full"
              and any("No incremental upload" in l and "corrupt" in l for _, l in r4["lines"]))
        check("Corrupt base: the agent unpacked exactly the client's tree", *same_tree(r4))

        print("\n5. One more file changed: the base the full upload reseeded works")
        time.sleep(1)  # the reseed runs after the upload's reply
        touch_one(3, "// change 3\n")
        r5 = client()
        check("After the reseed: incremental upload again", r5["rc"] == 0 and r5["job"].get("src_via") == "delta")
        check("After the reseed: the agent unpacked exactly the client's tree", *same_tree(r5))
        check("Hub keeps one base tree per project and platform", os.listdir(os.path.join(hub_home, "bases")) == ["app-android"],
              str(os.listdir(os.path.join(hub_home, "bases"))))
        left = [f for f in os.listdir(os.path.join(hub_home, "jobs")) if not f.endswith((".json", ".log"))]
        check("No source, manifest or temporary files left in jobs/", left == [], str(left))
    finally:
        stop.set()
        hub.terminate()
        hub.wait()
        print("Test directory: %s" % tmp)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
