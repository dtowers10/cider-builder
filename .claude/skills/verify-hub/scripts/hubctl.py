#!/usr/bin/env python3
"""Start, check and stop a disposable cider-build hub for verifying the panel and the client CLI.

    hubctl.py up [--run ID]           seeded hub from this checkout's bin/, on free 127.0.0.1 ports
    hubctl.py up --no-updates         the same with update_url off in its hub.json: hub updates are off
    hubctl.py up --real [URL]         read-only proxy: this checkout's panel, GETs forwarded to a real hub
                                      (default: the hub `bin/cider-build hub` prints)
    hubctl.py doctor [--run ID]       read-only: is this instance ours, current and alive? Exit 0 if so
    hubctl.py down [--run ID]         stop what this run started, delete its scratch dir, keep the evidence
    hubctl.py list                    runs that still have a scratch dir

Scratch state lives in /tmp/verify-hub/run-<ID>/ and evidence in /tmp/verify-hub/evidence/<ID>/.
--run defaults to $VERIFY_HUB_RUN, then to the only run that exists.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
ROOT = "/tmp/verify-hub"
EXT = {"ios": "app.tar.gz", "android": "apk"}
PROJECTS = {"demo": "expo", "shop": "react_native", "ledger": "ios_native", "scanner": "android_native"}
CLIENTS = ("elena", "ci-runner", "daniel")
# label: slots, ram_gb, free_gb, tools_ready, enabled, sends heartbeats, agent can update itself
MACS = {
    "mac-alpha": (2, 64, 21.5, True, True, True, True),
    "mac-beta": (1, 32, 9.0, True, True, True, True),
    "mac-epsilon": (1, 24, 18.0, False, True, True, True),
    "mac-gamma": (2, 48, 30.0, True, True, False, True),
    "mac-zeta": (2, 48, 40.0, True, False, True, False),
    "linux-delta": (1, 32, 12.0, True, True, True, True),
}
LINUX = {"linux-delta"}  # an x86-64 Linux machine: builds Android only
OLD_AGENT = "2026.10.3"
NEXT_SUBJECT = "Panel: show each build's estimated time left"
EXPECTED_STATES = {"mac-alpha": "online", "mac-beta": "online", "mac-epsilon": "no_tools", "mac-gamma": "stale",
                   "mac-zeta": "disabled", "linux-delta": "online"}
READ_PATHS = ("/api/state", "/api/history", "/api/cache", "/api/job", "/poll")


def saved_hub():
    """The hub this checkout's client uses, as `bin/cider-build hub` prints it."""
    r = subprocess.run([os.path.join(REPO, "bin", "cider-build"), "hub"], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        sys.exit("hubctl: up --real needs the hub's URL: up --real https://<hub>:4710, or a client set up with "
                 "`cider-build hub <URL>`")
    return r.stdout.splitlines()[0]


def run_dir(run):
    return os.path.join(ROOT, "run-" + run)


def evidence_dir(run):
    return os.path.join(ROOT, "evidence", run)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def request(method, url, body=None, timeout=10):
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def get_json(base, path):
    code, _, body = request("GET", base + path)
    if code != 200:
        raise RuntimeError("%s -> HTTP %d" % (path, code))
    return json.loads(body)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def load_state(run):
    with open(os.path.join(run_dir(run), "state.json")) as f:
        return json.load(f)


def pick_run(arg):
    run = arg or os.environ.get("VERIFY_HUB_RUN")
    if run:
        return run
    runs = existing_runs()
    if len(runs) == 1:
        return runs[0]
    sys.exit("hubctl: pass --run, one of: %s" % (", ".join(runs) or "(no runs; start one with `up`)"))


def existing_runs():
    if not os.path.isdir(ROOT):
        return []
    return sorted(d[4:] for d in os.listdir(ROOT) if d.startswith("run-"))


def panel_hashes():
    with open(os.path.join(REPO, "bin", "cider-build-panel.html"), encoding="utf-8") as f:
        text = f.read()
    return {tag: base64.b64encode(hashlib.sha256(re.findall(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)[0].encode())
                                  .digest()).decode() for tag in ("script", "style")}


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def started_by_run(pid, run):
    """The process carries this run's marker in its environment, so a reused PID is never mistaken for ours."""
    try:
        with open("/proc/%d/environ" % pid, "rb") as f:
            return ("VERIFY_HUB_RUN=" + run).encode() in f.read().split(b"\0")
    except OSError:
        return alive(pid)


# --- seed ------------------------------------------------------------------------------------------

def release_files():
    import importlib.machinery
    return importlib.machinery.SourceFileLoader("hub", os.path.join(REPO, "bin", "cider-build-hub")).load_module().RELEASE_FILES


def seed_repo(repo, home):
    """A local repository is the update source: commit A is this checkout's files, installed in bin/; B is one ahead."""
    def git(*args):
        return subprocess.check_output(["git", "-C", repo, "-c", "user.name=verify-hub", "-c", "user.email=verify@example.com"]
                                       + list(args)).decode().strip()
    subprocess.check_call(["git", "init", "-q", "-b", "main", repo])
    for src, dest, mode in release_files():
        for root in (repo, os.path.join(home, "bin")):
            path = os.path.join(root, src if root == repo else dest)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copy(os.path.join(REPO, src), path)
            os.chmod(path, mode)
    git("add", "-A")
    git("commit", "-q", "-m", "What the hub runs")
    with open(os.path.join(home, "bin", ".commit"), "w") as f:
        f.write(git("rev-parse", "HEAD") + "\n")
    with open(os.path.join(repo, "bin", "build.sh"), "a") as f:
        f.write("# next\n")
    git("commit", "-q", "-am", NEXT_SUBJECT)


def machine(label, tools):
    """What the agent on that machine reports: its OS, the platforms it builds, Xcode and its details."""
    if label in LINUX:
        return {"os": "linux", "platforms": ["android"] if tools else [], "xcode": None,
                "info": {"chip": "AMD EPYC 7B13", "model": "x86_64", "distro": "Ubuntu 24.04.3 LTS", "host": label,
                         "dns": label + ".example.ts.net", "tailnet": "example.ts.net"}}
    return {"os": "macos", "platforms": ["ios", "android"] if tools else [], "xcode": "16.4",
            "info": {"chip": "Apple M2 Pro", "model": "Mac14,12", "macos": "15.5", "host": label,
                     "dns": label + ".example.ts.net", "tailnet": "example.ts.net"}}


def seed(home, t0):
    for d in ("jobs", "workers", "cache", "bin"):
        os.makedirs(os.path.join(home, d))
    for label, (slots, ram, free, tools, enabled, beats, _) in MACS.items():
        write_json(os.path.join(home, "workers", label + ".json"), dict(machine(label, tools), **{
            "label": label, "enabled": enabled, "slots": slots, "user": "builder", "ram_gb": ram, "free_gb": free,
            "seen": t0 if beats else t0 - 3600, "boot": "boot-" + label, "running": [], "version": OLD_AGENT}))
    n = [0]

    def job(state, proj, plat, created, worker=None, started=None, finished=None, rc=None, log=""):
        n[0] += 1
        jid = "%x-%06x" % (int(created * 1000), n[0])
        write_json(os.path.join(home, "jobs", jid + ".json"), {
            "id": jid, "proj": proj, "key": "k%04d" % n[0], "plat": plat, "kind": PROJECTS[proj], "ext": EXT[plat],
            "cfg": {"MB_SCHEME": proj.title()}, "client": CLIENTS[n[0] % 3], "state": state, "worker": worker,
            "created": created, "started": started, "finished": finished, "rc": rc, "retries": 0,
            "attempt": 1 if worker else 0, "src": True, "seen": t0, "waiters": {"seed%d" % n[0]: t0},
            "log_offset": 0, "delivered_boot": None})
        with open(os.path.join(home, "jobs", jid + ".log"), "w") as f:
            f.write(log)
        return jid

    running = {
        job("building", "demo", "ios", t0 - 300, "mac-alpha", t0 - 290, log="cider-build: building demo on mac-alpha\n"): "mac-alpha",
        job("building", "shop", "android", t0 - 120, "mac-alpha", t0 - 110, log="> Task :app:assembleRelease\n"): "mac-alpha",
        job("building", "ledger", "ios", t0 - 60, "mac-beta", t0 - 55, log="** BUILD START **\n"): "mac-beta",
        job("building", "scanner", "android", t0 - 90, "linux-delta", t0 - 85, log="> Task :app:mergeDebugResources\n"): "linux-delta",
    }
    job("queued", "scanner", "android", t0 - 40)
    job("queued", "demo", "android", t0 - 30)
    for i in range(42):
        proj = sorted(PROJECTS)[i % 4]
        plat = "android" if proj == "scanner" or i % 5 == 0 else "ios"
        fin = t0 - 600 - i * 9000
        state = "failed" if i % 7 == 2 else "cancelled" if i % 11 == 4 else "done"
        job(state, proj, plat, fin - 200, ("mac-alpha", "mac-beta", "mac-gamma")[i % 3], fin - 180, fin,
            {"done": 0, "failed": 65, "cancelled": None}[state],
            log="cider-build: attempt %d\n%s\n" % (i, "** BUILD FAILED **" if state == "failed" else "** BUILD SUCCEEDED **"))
    affinity = {}
    for proj, kind in sorted(PROJECTS.items()):
        plat = "android" if kind == "android_native" else "ios"
        os.makedirs(os.path.join(home, "cache", proj))
        for k in (1, 2):
            with open(os.path.join(home, "cache", proj, "k%04d-%s.%s" % (k, plat, EXT[plat])), "wb") as f:
                f.write(b"\0" * 150000 * k)
        affinity["%s-%s" % (proj, plat)] = ("mac-alpha", "mac-beta")[len(affinity) % 2]
    write_json(os.path.join(home, "affinity.json"), affinity)
    return running


# --- fleet: plays the Macs over the same HTTP calls bin/cider-build-worker makes ----------------------

def fleet(run):
    st = load_state(run)
    base = st["url"].rstrip("/")
    running = {label: {} for label in MACS}
    for jid, label in st["seed_running"].items():
        running[label][jid] = "1"
    version = {label: OLD_AGENT for label in MACS}
    tick = 0
    while True:
        for label, (slots, ram, free, tools, enabled, beats, self_update) in MACS.items():
            if not beats:
                continue
            body = dict(machine(label, tools), label=label, boot="boot-" + label, running=sorted(running[label]),
                        ram_gb=ram, free_gb=free, version=version[label], user="builder", self_update=self_update)
            try:
                code, _, raw = request("POST", base + "/w/heartbeat", json.dumps(body).encode())
                reply = json.loads(raw) if code == 200 else {}
            except (OSError, ValueError):
                continue
            for jid in reply.get("cancel", []):
                running[label].pop(jid, None)
            for j in reply.get("jobs", []):
                running[label][j["id"]] = str(j["attempt"])
            if reply.get("update"):
                # A real agent first waits for its builds to end; this one reports the new version on its next beat.
                version[label] = reply["update"]["version"]
            for jid, attempt in list(running[label].items()):
                line = "\x1b[32m>\x1b[0m CompileSwift normal arm64 Module%d.swift (%d/400)\n" % (tick, tick)
                q = urllib.parse.urlencode({"job": jid, "label": label, "attempt": attempt, "offset": 10 ** 12})
                try:
                    if request("POST", base + "/w/log?" + q, line.encode())[0] == 409:
                        running[label].pop(jid, None)
                except OSError:
                    pass
        try:
            active = get_json(base, "/api/state")["active"]
            if not any(j["state"] == "queued" and not j["src"] for j in active):
                form = urllib.parse.urlencode({"proj": "shop", "key": "nosrc%d" % tick, "plat": "ios",
                                               "kind": "react_native", "waiter": "verify-client", "client": "elena"})
                request("POST", base + "/submit", form.encode())
        except (OSError, RuntimeError, ValueError):
            pass
        tick += 1
        time.sleep(2)


# --- real hub, read-only ----------------------------------------------------------------------------

def proxy(run):
    st = load_state(run)
    hub = None

    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, ctype, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/panel"):
                body, headers = hub.panel()
                return self.send(200, body, "text/html; charset=utf-8", headers)
            if path.startswith("/fonts/"):
                return self.send(200, hub.font(path.split("/")[-1]), "font/woff2")
            if path not in READ_PATHS:
                return self.send(404, b"verify-hub proxy: read-only, path not forwarded\n", "text/plain")
            code, headers, body = request("GET", st["real"] + self.path, timeout=15)
            self.send(code, body, headers.get("Content-Type", "application/octet-stream"))

        def refuse(self):
            self.send(405, b"verify-hub proxy: read-only, writes never reach the real hub\n", "text/plain")

        do_POST = do_PUT = do_DELETE = refuse

    import importlib.machinery
    os.environ["CIDER_BUILD_HOME"] = st["home"]
    hub = importlib.machinery.SourceFileLoader("hub", os.path.join(REPO, "bin", "cider-build-hub")).load_module()
    http.server.ThreadingHTTPServer(("127.0.0.1", st["port"]), Proxy).serve_forever()


# --- commands ---------------------------------------------------------------------------------------

def spawn(run, args, log, env=None):
    env = dict(env or os.environ, VERIFY_HUB_RUN=run)
    return subprocess.Popen(args, env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT, start_new_session=True).pid


def up(args):
    real = None if args.real is None else (args.real or saved_hub()).rstrip("/")
    run = args.run or os.environ.get("VERIFY_HUB_RUN") or time.strftime("%H%M%S-") + secrets.token_hex(2)
    rd, ev = run_dir(run), evidence_dir(run)
    if os.path.exists(rd):
        sys.exit("hubctl: run %s already exists; `down --run %s` first" % (run, run))
    os.makedirs(rd)
    os.makedirs(ev, exist_ok=True)
    home, fakebin = os.path.join(rd, "home"), os.path.join(rd, "fakebin")
    port, tailnet_port = free_port(), free_port()
    dns = "verify-hub-%s.example.ts.net" % run
    st = {"run": run, "mode": "real" if real else "seeded", "real": real, "updates": not args.no_updates, "home": home,
          "port": port, "tailnet_port": tailnet_port, "url": "http://127.0.0.1:%d/" % port, "evidence": ev, "pids": {},
          "canonical": real or "https://%s:%d" % (dns, port)}
    me = [sys.executable, os.path.abspath(__file__)]
    if real:
        os.makedirs(home)
        write_json(os.path.join(rd, "state.json"), st)
        st["pids"]["proxy"] = spawn(run, me + ["_proxy", "--run", run], os.path.join(rd, "proxy.log"))
    else:
        st["seed_running"] = seed(home, time.time())
        seed_repo(os.path.join(rd, "repo"), home)
        write_json(os.path.join(home, "hub.json"), {"update_url": os.path.join(rd, "repo") if st["updates"] else "off"})
        os.makedirs(fakebin)
        with open(os.path.join(fakebin, "tailscale"), "w") as f:
            f.write("#!/bin/sh\necho '%s'\n" % json.dumps({"BackendState": "Running", "Self": {
                "TailscaleIPs": ["127.0.0.1"], "DNSName": dns + ".", "HostName": "verify-hub-" + run}}))
        os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
        env = dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port), CIDER_BUILD_TAILNET_PORT=str(tailnet_port),
                   HOME=rd, PATH=fakebin + ":/usr/bin:/bin")
        st["pids"]["hub"] = spawn(run, [sys.executable, os.path.join(REPO, "bin", "cider-build-hub")],
                                  os.path.join(rd, "hub.log"), env)
        write_json(os.path.join(rd, "state.json"), st)
        wait(lambda: get_json(st["url"].rstrip("/"), "/api/state"), "hub answering /api/state", rd)
        st["pids"]["fleet"] = spawn(run, me + ["_fleet", "--run", run], os.path.join(rd, "fleet.log"))
    write_json(os.path.join(rd, "state.json"), st)
    wait(lambda: usable(st), "real hub readable" if real else "seeded data visible through the API", rd)
    if real:
        st["canonical"] = get_json(st["url"].rstrip("/"), "/api/state")["hub"]["url"]
        write_json(os.path.join(rd, "state.json"), st)
    print("READY run=%s url=%s mode=%s evidence=%s" % (run, st["url"], st["mode"], ev))
    print("export VERIFY_HUB_RUN=%s" % run)


def wait(probe, what, rd, timeout=30):
    end, last = time.time() + timeout, None
    while time.time() < end:
        try:
            if probe() is not False:
                return
        except Exception as e:  # noqa: BLE001 - any failure means "not ready yet"
            last = e
        time.sleep(0.3)
    sys.exit("hubctl: not ready after %d s (%s): %s. Logs in %s; run `down` to clean up." % (timeout, what, last, rd))


def usable(st):
    base = st["url"].rstrip("/")
    s = get_json(base, "/api/state")
    if st["mode"] == "real":
        return bool(s["hub"]["url"])
    states = {w["label"]: w["state"] for w in s["workers"]}
    building = [j for j in s["active"] if j["state"] == "building"]
    rel = s["release"]
    updates = (rel["available"] and rel["behind"] == 1 and rel["phase"] == "idle" if st["updates"]
               else rel["source"] is None and rel["checked"] is None)
    return (states == EXPECTED_STATES and len(building) == 4 and s["hub"]["url"] == st["canonical"] and updates
            and sum(1 for w in s["workers"] if w["self_update"] and not w["agent_current"]) == 4
            and len(get_json(base, "/api/history")["jobs"]) >= 42 and len(get_json(base, "/api/cache")["projects"]) == 4
            and request("GET", "http://127.0.0.1:%d/join" % st["tailnet_port"])[0] == 200)


def doctor(args):
    run = pick_run(args.run)
    try:
        st = load_state(run)
    except OSError:
        sys.exit("FAIL  no state for run %s in %s" % (run, run_dir(run)))
    base, bad = st["url"].rstrip("/"), 0

    def check(ok, what):
        nonlocal bad
        print("%s  %s" % ("OK  " if ok else "FAIL", what))
        bad += not ok

    for name, pid in st["pids"].items():
        check(alive(pid) and started_by_run(pid, run), "%s (pid %d) is alive and was started by run %s" % (name, pid, run))
    try:
        s = get_json(base, "/api/state")
        check(s["hub"]["url"] == st["canonical"], "%s answers as %s, so the port is ours" % (base, st["canonical"]))
        if st["mode"] == "seeded":
            fresh = [w for w in s["workers"] if w["state"] != "stale" and s["now"] - w["seen"] < 10]
            check(len(fresh) == 4, "fake Macs sent a heartbeat in the last 10 s (%d of 4)" % len(fresh))
        code, headers, _ = request("GET", base + "/")
        csp = headers.get("Content-Security-Policy") or ""
        h = panel_hashes()
        check(code == 200 and all("'sha256-%s'" % h[t] in csp for t in h),
              "the panel served is this checkout's bin/cider-build-panel.html (CSP hashes match)")
        if st["mode"] == "real":
            code = request("POST", base + "/detach?job=doctor-probe")[0]
            check(code == 405, "the proxy refuses writes (POST -> %d)" % code)
    except (OSError, RuntimeError, ValueError, KeyError) as e:
        check(False, "%s readable: %s" % (base, e))
    print("evidence: %s" % st["evidence"])
    sys.exit(1 if bad else 0)


def down(args):
    run = pick_run(args.run)
    rd = run_dir(run)
    try:
        st = load_state(run)
        pids = list(st["pids"].values())
    except OSError:
        st, pids = {}, []
    chrome = os.path.join(rd, "chrome.pid")
    if os.path.exists(chrome):
        with open(chrome) as f:
            pids.append(int(f.read().strip()))
    for pid in pids:
        if alive(pid) and started_by_run(pid, run):
            os.killpg(pid, signal.SIGTERM)
    time.sleep(0.5)
    for pid in pids:
        if alive(pid) and started_by_run(pid, run):
            os.killpg(pid, signal.SIGKILL)
    shutil.rmtree(rd, ignore_errors=True)
    print("stopped run %s; evidence kept in %s" % (run, evidence_dir(run)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("up", "doctor", "down", "list", "_fleet", "_proxy"))
    p.add_argument("--run")
    p.add_argument("--real", nargs="?", const="", metavar="URL",
                   help="with up: read-only proxy to the hub at URL (default: the one `bin/cider-build hub` prints)")
    p.add_argument("--no-updates", action="store_true", help="with up: update_url off in the seeded hub.json")
    args = p.parse_args()
    if args.command == "up":
        up(args)
    elif args.command == "doctor":
        doctor(args)
    elif args.command == "down":
        down(args)
    elif args.command == "list":
        print("\n".join(existing_runs()))
    elif args.command == "_fleet":
        fleet(args.run)
    else:
        proxy(args.run)


if __name__ == "__main__":
    main()
