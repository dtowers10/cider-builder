#!/usr/bin/env python3
"""Updating the hub from its git repository and the agents from the hub, with the real hub and agent.

A local git repository is the update source (update_url in the hub's hub.json). Commit A is installed in a
temporary CIDER_BUILD_HOME/bin and the hub runs from there, so an update replaces the files of the running hub and its
exit plays launchd's restart. Then the agent side over HTTP, and the real cider-build-worker loaded as a module
(its own HOME, a fake Machine) updating itself from that hub. Touches no fleet and no network. Exits 0 if all
checks pass.
"""
import hashlib
import importlib.machinery
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(line_buffering=True)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="cider-build-update-")
gitrepo, home, fakebin, user_home, agent_home = (os.path.join(tmp, d) for d in ("repo", "hub", "fakebin", "user", "agent"))
BIN = os.path.join(home, "bin")
for d in (gitrepo, BIN, fakebin, user_home, os.path.join(agent_home, "cider-build")):
    os.makedirs(d)

os.environ["CIDER_BUILD_HOME"] = os.path.join(tmp, "unused")
HUB = importlib.machinery.SourceFileLoader("hub", os.path.join(REPO, "bin", "cider-build-hub")).load_module()
FILES = HUB.RELEASE_FILES

failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok
    return ok


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def git(*args):
    return subprocess.check_output(["git", "-C", gitrepo, "-c", "user.name=test", "-c", "user.email=test@example.com"]
                                   + list(args)).decode().strip()


def commit(subject, changes):
    for src, data in changes.items():
        with open(os.path.join(gitrepo, src), "wb") as f:
            f.write(data)
    git("add", "-A")
    git("commit", "-q", "-m", subject)
    return git("rev-parse", "HEAD")


def at(sha, src):
    return subprocess.check_output(["git", "-C", gitrepo, "show", "%s:%s" % (sha, src)])


def installed():
    out = {}
    for _, dest, _ in FILES:
        with open(os.path.join(BIN, dest), "rb") as f:
            out[dest] = f.read()
    return out


def release_of(sha):
    return {dest: at(sha, src) for src, dest, _ in FILES}


def call(method, path, body=None):
    req = urllib.request.Request(base + path, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def state():
    return json.loads(call("GET", "/api/state")[1])


def until(probe, what, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            got = probe()
            if got:
                return got
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("timed out waiting for " + what)


def start_hub():
    p = subprocess.Popen([sys.executable, os.path.join(BIN, "cider-build-hub")], env=env,
                         stderr=open(os.path.join(tmp, "hub.log"), "a"))
    until(lambda: call("GET", "/status")[0] == 200, "the hub to answer")
    return p


def checked(after=0.0):
    """Waits for a check that ended after `after` and returns the release state."""
    return until(lambda: (lambda r: r if r["phase"] == "idle" and (r["checked"] or 0) > after else None)(state()["release"]),
                 "a finished check")


def beat(label, version, self_update=True, running=()):
    body = {"label": label, "boot": "boot-" + label, "user": "test", "ram_gb": 32, "free_gb": 16, "running": list(running),
            "tools_ready": True, "xcode": "16.0", "version": version, "info": {}, "self_update": self_update}
    code, text = call("POST", "/w/heartbeat", json.dumps(body).encode())
    assert code == 200, text
    return json.loads(text)


def worker(label):
    return next(w for w in state()["workers"] if w["label"] == label)


# --- A in the repository and installed --------------------------------------------------------------
for src, _, _ in FILES:
    os.makedirs(os.path.dirname(os.path.join(gitrepo, src)), exist_ok=True)
subprocess.check_call(["git", "init", "-q", "-b", "main", gitrepo])
A = commit("A: the working copy", {src: open(os.path.join(REPO, src), "rb").read() for src, _, _ in FILES})
for src, dest, mode in FILES:
    os.makedirs(os.path.dirname(os.path.join(BIN, dest)), exist_ok=True)
    shutil.copy(os.path.join(gitrepo, src), os.path.join(BIN, dest))
    os.chmod(os.path.join(BIN, dest), mode)
with open(os.path.join(BIN, ".commit"), "w") as f:
    f.write(A + "\n")

with open(os.path.join(fakebin, "tailscale"), "w") as f:
    f.write("#!/bin/sh\nexit 1\n")  # the test hub does not listen on the tailnet
os.chmod(os.path.join(fakebin, "tailscale"), 0o755)
with open(os.path.join(home, "hub.json"), "w") as f:
    json.dump({"update_url": gitrepo, "exclude": ["mac-off"]}, f)
settings = open(os.path.join(home, "hub.json"), "rb").read()
port = free_port()
base = "http://127.0.0.1:%d" % port
env = dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port), CIDER_BUILD_TAILNET_PORT=str(free_port()),
           HOME=user_home, PATH=fakebin + ":/usr/bin:/bin")
hub = None
try:
    hub = start_hub()
    r = checked()
    check(not r["available"] and r["installed"] == A and r["error"] is None,
          "the hub checks the repository on its own after starting: up to date at A")
    check(r["source"] == {"url": gitrepo, "branch": "main", "check_s": 1800}, "/api/state names the update source from hub.json")

    worker_b = at(A, "bin/cider-build-worker") + b"# B\n"
    B = commit("B: change the worker and the panel", {"bin/cider-build-worker": worker_b,
                                                       "bin/cider-build-panel.html": at(A, "bin/cider-build-panel.html") + b"<!-- B -->\n"})
    t = time.time()
    check(call("POST", "/hub/check") == (200, "checking\n"), "POST /hub/check starts a check")
    r = checked(t)
    check(r["available"] and r["behind"] == 1 and r["remote"]["commit"] == B and r["installed"] == A
          and [c["subject"] for c in r["commits"]] == ["B: change the worker and the panel"],
          "after commit B: update available, 1 behind, with B's subject (%s)" % json.dumps(r["commits"]))

    check(call("POST", "/hub/update") == (200, "updating\n"), "POST /hub/update starts the update")
    check(call("POST", "/hub/check")[0] == 409, "a second job while updating gets 409")
    rc = hub.wait(60)
    check(rc == 0, "the hub exits by itself with 0 after installing B (rc=%s)" % rc)
    check(installed() == release_of(B), "bin/ holds B's files")
    check(open(os.path.join(BIN, ".commit")).read().strip() == B, "bin/.commit names B")
    check(all(open(os.path.join(BIN, ".previous", dest), "rb").read() == data for dest, data in release_of(A).items())
          and open(os.path.join(BIN, ".previous", ".commit")).read().strip() == A,
          "bin/.previous holds A's files and .commit for a manual rollback")
    check(not os.path.exists(os.path.join(BIN, ".staged")), "nothing is left staged")
    check(open(os.path.join(home, "hub.json"), "rb").read() == settings, "hub.json is byte-identical after the update")
    check(oct(os.stat(os.path.join(BIN, "cider-build-panel.html")).st_mode & 0o777) == "0o644"
          and oct(os.stat(os.path.join(BIN, "cider-build-hub")).st_mode & 0o777) == "0o755", "modes 644 and 755 as installed")

    hub = start_hub()  # what launchd does
    r = checked()
    check(not r["available"] and r["installed"] == B and r["behind"] == 0, "restarted: up to date, installed B")
    check(b"<!-- B -->" in urllib.request.urlopen(base + "/").read(), "the restarted hub serves B's panel")

    C = commit("C: a hub that does not compile", {"bin/cider-build-hub": at(B, "bin/cider-build-hub") + b"\ndef broken(:\n"})
    t = time.time()
    call("POST", "/hub/check")
    check(checked(t)["available"], "after commit C: update available")
    t = time.time()
    check(call("POST", "/hub/update")[0] == 200, "POST /hub/update accepted for C")
    r = until(lambda: (lambda r: r if r["phase"] == "idle" and r["error"] else None)(state()["release"]), "the refusal")
    check("cider-build-hub does not compile" in r["error"], "C is refused: %s" % r["error"])
    check(installed() == release_of(B) and not os.path.exists(os.path.join(BIN, ".staged")),
          "bin/ still holds B and nothing is staged")
    check(hub.poll() is None and call("GET", "/status")[0] == 200, "the hub keeps serving")

    hub_d = at(B, "bin/cider-build-hub").replace(b"\ndef main():", b"\nraise SystemExit(3)\n\n\ndef main():", 1)
    D = commit("D: a hub that compiles but does not start", {"bin/cider-build-hub": hub_d})
    t = time.time()
    call("POST", "/hub/check")
    checked(t)
    call("POST", "/hub/update")
    r = until(lambda: (lambda r: r if r["phase"] == "idle" and r["error"] else None)(state()["release"]), "the refusal", 40)
    check("the new hub did not start" in r["error"], "D is refused by the test start: %s" % r["error"])
    check(installed() == release_of(B) and hub.poll() is None, "bin/ still holds B and the hub keeps serving")

    hub_b = at(B, "bin/cider-build-hub")
    hub_e = hub_b.replace(b"def names(v):\n", b"def names(v):\n    raise ValueError(\"this release reads it differently\")\n", 1)
    assert hub_e != hub_b, "E's hub must differ from B's"
    commit("E: a hub that cannot read the exclude in the live hub.json", {"bin/cider-build-hub": hub_e})
    t = time.time()
    call("POST", "/hub/check")
    checked(t)
    call("POST", "/hub/update")
    r = until(lambda: (lambda r: r if r["phase"] == "idle" and r["error"] else None)(state()["release"]), "the refusal", 40)
    check("the new hub did not start" in r["error"] and "hub.json: exclude: this release reads it differently" in r["error"],
          "E is refused because the test start reads the live hub.json: %s" % r["error"])
    check(installed() == release_of(B) and hub.poll() is None, "bin/ still holds B and the hub keeps serving")

    # --- agents --------------------------------------------------------------------------------------
    agent = hashlib.sha256(open(os.path.join(BIN, "cider-build-worker"), "rb").read() + b"\0"
                           + open(os.path.join(BIN, "build.sh"), "rb").read()).hexdigest()[:12]
    check(state()["agent"] == agent, "/api/state names the agent version the hub hands out")
    call("PUT", "/workers/mac-up-01?slots=1")
    call("PUT", "/workers/mac-legacy?slots=1")
    beat("mac-up-01", "old")
    beat("mac-legacy", "3", self_update=False)
    w = worker("mac-up-01")
    check(w["state"] == "online" and not w["agent_current"] and w["self_update"], "an old agent shows online and outdated")
    code, text = call("POST", "/workers/mac-legacy/update")
    check(code == 409 and "cider-build add mac-legacy" in text, "an agent without self-update: 409 (%s)" % text.strip())
    check(call("POST", "/workers/nobody/update")[0] == 404, "an unknown Mac: 404")
    call("DELETE", "/workers/mac-legacy")
    check(call("POST", "/workers/mac-up-01/update") == (200, "updating mac-up-01\n"), "POST /workers/mac-up-01/update")
    w = worker("mac-up-01")
    check(w["state"] == "updating" and w["update"], "the Mac shows updating")

    form = urllib.parse.urlencode({"proj": "app", "key": "k1", "plat": "ios", "kind": "expo", "waiter": "c1"}).encode()
    jid = call("POST", "/submit", form)[1].split()[1]
    call("PUT", "/source?job=" + jid, b"code")
    resp = beat("mac-up-01", "old")
    check(resp["jobs"] == [] and resp.get("update") == {"version": agent},
          "while updating it gets no job and the heartbeat asks for agent %s" % agent)
    resp = beat("mac-up-01", agent)
    w = worker("mac-up-01")
    check("update" not in resp and [j["id"] for j in resp["jobs"]] == [jid] and w["agent_current"] and not w["update"],
          "a heartbeat with the new version clears the flag and the queued job is assigned")
    beat("mac-up-01", agent, running=[jid])
    check(worker("mac-up-01")["state"] == "online", "and the Mac is online again")
    check(call("POST", "/workers/mac-up-01/update")[0] == 409, "asking a current agent to update: 409")

    # --- the real agent ------------------------------------------------------------------------------
    adir = os.path.join(agent_home, "cider-build")
    shutil.copy(os.path.join(REPO, "bin", "cider-build-worker"), os.path.join(adir, "cider-build-worker"))
    with open(os.path.join(adir, "build.sh"), "wb") as f:
        f.write(b"#!/bin/bash\necho old build.sh\n")
    with open(os.path.join(adir, "worker.json"), "w") as f:
        json.dump({"label": "mac-agent", "hub": base}, f)
    os.environ["HOME"] = agent_home
    W = importlib.machinery.SourceFileLoader("worker", os.path.join(adir, "cider-build-worker")).load_module()
    before = {f: open(os.path.join(adir, f), "rb").read() for f in ("cider-build-worker", "build.sh")}
    check(W.VERSION == W.agent_version(before["cider-build-worker"], before["build.sh"]) and W.VERSION != agent,
          "the agent's VERSION is the hash of its own files (%s)" % W.VERSION)
    try:
        W.update_agent("0123456789ab")
        check(False, "update_agent with a wrong version raises")
    except RuntimeError as e:
        check("0123456789ab" in str(e) and agent in str(e), "update_agent with a wrong version raises: %s" % e)
    check({f: open(os.path.join(adir, f), "rb").read() for f in before} == before
          and not [f for f in os.listdir(adir) if f.endswith(".new")], "and leaves the agent's files untouched")

    class Exited(Exception):
        pass

    class Machine:
        ram_gb, free_gb, tools_ready, xcode, info = 32, 16.0, True, "16.0", {}

        def refresh(self):
            pass

    sleeps = []

    def sleep(s):
        """Between heartbeats: after the first one, the operator asks for the update from the panel."""
        sleeps.append(s)
        if len(sleeps) == 1:
            sleeps.append(call("POST", "/workers/mac-agent/update"))
        if len(sleeps) > 10:
            raise RuntimeError("the agent did not update after 5 heartbeats")

    def exit_(code):
        raise Exited(code)

    call("PUT", "/workers/mac-agent?slots=1")
    real_exit, W.Machine = os._exit, Machine
    W.time = types.SimpleNamespace(time=time.time, strftime=time.strftime, sleep=sleep)
    os._exit = exit_
    try:
        W.main()
    except Exited as e:
        check(e.args == (0,), "the agent's loop updates itself and exits 0 for launchd (%s)" % (sleeps[1],))
    finally:
        os._exit = real_exit
    got = {f: open(os.path.join(adir, f), "rb").read() for f in before}
    check(got["cider-build-worker"] == open(os.path.join(BIN, "cider-build-worker"), "rb").read()
          and got["build.sh"] == open(os.path.join(BIN, "build.sh"), "rb").read(), "its files are now the hub's")
    check(W.agent_version(got["cider-build-worker"], got["build.sh"]) == agent, "and hash to the version the hub asked for")
    check(not [f for f in os.listdir(adir) if f.endswith(".new")]
          and all(os.stat(os.path.join(adir, f)).st_mode & 0o777 == 0o755 for f in before), "no leftovers, both 755")
except (OSError, ValueError, KeyError, IndexError, RuntimeError, AssertionError, subprocess.SubprocessError) as e:
    check(False, "unexpected error: %r" % e)
finally:
    if hub and hub.poll() is None:
        hub.terminate()
        hub.wait()
    print("hub log, repository and CIDER_BUILD_HOME in %s" % tmp)
sys.exit(1 if failures else 0)
