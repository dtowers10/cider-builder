#!/usr/bin/env python3
"""Which machine gets which platform, against a real hub, without touching the fleet.

Starts bin/cider-build-hub on 127.0.0.1 with a temporary CIDER_BUILD_HOME and a free port, with BEAT_TTL cut to
2 s in this process only, without listening on the tailnet or running a drain command. Plays a Mac (iOS and
Android), a Linux machine (Android only) and an agent from before Linux builders over HTTP, and checks that Android
goes to Linux while one is in the pool, that a Linux machine never gets iOS, and that Android falls back to the Macs
when no Linux machine is left. Exits 0 if every check passes.
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
BEAT_TTL = 2

LOADER = """
import importlib.machinery, importlib.util, sys
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("hub", sys.argv[1])
hub = importlib.util.module_from_spec(importlib.util.spec_from_loader("hub", loader))
loader.exec_module(hub)
hub.BEAT_TTL = int(sys.argv[2])
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


def beat(label, osname, platforms, running=()):
    body = {"label": label, "boot": "boot1", "user": "test", "ram_gb": 32, "free_gb": 20, "running": list(running),
            "os": osname, "platforms": platforms, "xcode": "16.0" if osname == "macos" else None, "version": "3",
            "info": {}}
    return [j["id"] for j in json.loads(call("POST", "/w/heartbeat", json.dumps(body).encode()))["jobs"]]


def legacy_beat(label):
    body = {"label": label, "boot": "boot1", "user": "test", "ram_gb": 32, "free_gb": 20, "running": [],
            "tools_ready": True, "xcode": "16.0", "version": "3", "info": {}}
    return [j["id"] for j in json.loads(call("POST", "/w/heartbeat", json.dumps(body).encode()))["jobs"]]


def submit(key, plat, kind):
    jid = call("POST", "/submit", ("proj=app&key=%s&plat=%s&kind=%s&waiter=w-%s" % (key, plat, kind, key)).encode()).split()[1]
    call("PUT", "/source?job=" + jid, b"source")
    return jid


def job(jid):
    return json.loads(call("GET", "/api/job?job=" + jid))["job"]


def workers():
    return {w["label"]: w for w in json.loads(call("GET", "/api/state"))["workers"]}


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
hub = subprocess.Popen([sys.executable, "-c", LOADER, HUB, str(BEAT_TTL)], env=env,
                       stderr=open(os.path.join(home, "hub.err"), "w"))
try:
    for _ in range(50):
        try:
            call("GET", "/status")
            break
        except OSError:
            time.sleep(0.1)
    for label in ("mac-1", "linux-1"):
        call("PUT", "/workers/%s?slots=2&ram=32" % label)
    beat("mac-1", "macos", ["ios", "android"])
    beat("linux-1", "linux", ["android"])

    ws = workers()
    check(ws["linux-1"]["os"] == "linux" and ws["linux-1"]["platforms"] == ["android"]
          and ws["mac-1"]["platforms"] == ["ios", "android"], "/api/state shows each machine's OS and platforms")
    check(ws["linux-1"]["state"] == "online", "a Linux machine with the Android tools is online")
    status = call("GET", "/status")
    check("android" in status.split("linux-1", 1)[1].split("\n", 1)[0], "cider-build status lists what linux-1 builds")

    a1 = submit("a1", "android", "expo")
    check(beat("mac-1", "macos", ["ios", "android"]) == [], "with a Linux machine in the pool, the Mac gets no Android job")
    check(beat("linux-1", "linux", ["android"]) == [a1], "the Linux machine gets the Android job")

    i1 = submit("i1", "ios", "expo")
    check(beat("linux-1", "linux", ["android", "ios"], [a1]) == [], "a Linux machine never gets iOS, whatever it claims")
    check(beat("mac-1", "macos", ["ios", "android"]) == [i1], "the iOS job goes to the Mac")

    a2 = submit("a2", "android", "android_native")
    a3 = submit("a3", "android", "react_native")
    check(beat("mac-1", "macos", ["ios", "android"], [i1]) == [],
          "with the Linux machine full, Android waits for it instead of taking the Mac")
    check(beat("linux-1", "linux", ["android"], [a1]) == [a2], "and takes the Linux machine's free slot")
    check(job(a3)["state"] == "queued", "a third Android job waits in the queue")

    deadline = time.time() + BEAT_TTL + 5
    got = []
    while not got and time.time() < deadline:
        time.sleep(0.5)
        got = beat("mac-1", "macos", ["ios", "android"], [i1])
    check(got == [a3], "once the Linux machine stops sending heartbeats, Android falls back to the Mac")

    beat("linux-2", "linux", [])
    call("PUT", "/workers/linux-2?slots=1&ram=16")
    check(workers()["linux-2"]["state"] == "no_tools", "a Linux machine without the Android tools shows missing tools")

    call("PUT", "/workers/mac-old?slots=1&ram=32")
    legacy_beat("mac-old")
    old = workers()["mac-old"]
    check(old["os"] == "macos" and old["platforms"] == ["ios", "android"] and old["state"] == "online",
          "an agent from before Linux builders (tools_ready only) counts as a Mac that builds both")
finally:
    hub.terminate()
    hub.wait()

print("temporary hub at %s, CIDER_BUILD_HOME=%s" % (base, home))
sys.exit(1 if failures else 0)
