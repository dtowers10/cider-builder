#!/usr/bin/env python3
"""End-to-end smoke test of bin/cider-build-hub with no Macs, no tailnet and no fleet.

Starts the hub as a separate process with a temporary CIDER_BUILD_HOME on free ports, whose hub.json excludes one
Mac and drains another. A fake `tailscale` on PATH reports 127.0.0.1 as the tailnet IP, so /join is served on
127.0.0.1. Plays a 1-slot Mac over HTTP and asserts only what clients, Macs and browsers see. Exits 0 if every check
passes.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL = "mac-smoke-01"
HOSTNAME = "hub-smoke"
DNS = HOSTNAME + ".example.ts.net"
ARTIFACT = b"fake .app.tar.gz"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.headers, r.read()


def answer(method, path):
    """(status, body) without raising on 4xx and 5xx."""
    try:
        code, _, body = call(method, base + path)
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    return code, body.decode()


def hub(method, path, body=None):
    return call(method, base + path, body)[2].decode()


def beat(running, label=LABEL):
    body = {"label": label, "boot": "boot1", "user": "smoke", "ram_gb": 32, "free_gb": 20, "running": running,
            "tools_ready": True, "xcode": "16.0", "version": "3", "info": {}}
    return json.loads(hub("POST", "/w/heartbeat", json.dumps(body).encode()))


def submit(key):
    form = urllib.parse.urlencode({"proj": "smoke", "key": key, "plat": "ios", "kind": "expo", "waiter": "cli1"})
    return hub("POST", "/submit", form.encode()).split()


def wait_up(url):
    for _ in range(100):
        try:
            return call("GET", url)
        except OSError:
            time.sleep(0.1)
    return call("GET", url)


failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


tmp = tempfile.mkdtemp(prefix="cider-build-smoke-")
home, fakebin = os.path.join(tmp, "hub"), os.path.join(tmp, "fakebin")
os.makedirs(os.path.join(home, "bin"))
os.makedirs(fakebin)
shutil.copy(os.path.join(REPO, "install.sh"), os.path.join(home, "bin", "install.sh"))
with open(os.path.join(home, "hub.json"), "w") as f:
    json.dump({"exclude": ["mac-off"], "drain_command": "echo mac-drained"}, f)
status = {"BackendState": "Running", "Self": {"TailscaleIPs": ["127.0.0.1"], "DNSName": DNS + ".", "HostName": HOSTNAME}}
with open(os.path.join(fakebin, "tailscale"), "w") as f:
    f.write("#!/bin/sh\necho '%s'\n" % json.dumps(status))
os.chmod(os.path.join(fakebin, "tailscale"), 0o755)

port, tailnet_port = free_port(), free_port()
base = "http://127.0.0.1:%d" % port
env = dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port), CIDER_BUILD_TAILNET_PORT=str(tailnet_port),
           PATH=fakebin + ":/usr/bin:/bin")
proc = subprocess.Popen([sys.executable, os.path.join(REPO, "bin", "cider-build-hub")], env=env,
                        stderr=open(os.path.join(tmp, "hub.log"), "w"))
try:
    code, _, _ = wait_up(base + "/status")
    check(code == 200, "GET /status answers 200")

    code, headers, html = call("GET", base + "/")
    csp = headers.get("Content-Security-Policy") or ""
    inline = [re.search(b"<%s>(.*?)</%s>" % (tag, tag), html, re.S) for tag in (b"script", b"style")]
    check(code == 200 and "default-src 'none'" in csp, "GET / serves the panel with a default-deny CSP")
    check(all(m and "'sha256-%s'" % base64.b64encode(hashlib.sha256(m.group(1)).digest()).decode() in csp for m in inline),
          "the panel CSP allows its inline <script> and <style> by hash")

    code, _, join = wait_up("http://127.0.0.1:%d/join" % tailnet_port)
    check(code == 200 and ("export CIDER_BUILD_HUB=https://%s:%d" % (DNS, port)).encode() in join,
          "GET /join on the tailnet port points the Mac at the hub's tailnet name")
    check(subprocess.run(["bash", "-n"], input=join).returncode == 0, "the /join script parses with bash -n")

    with open(os.path.join(REPO, "install.sh"), "rb") as f:
        install = f.read()
    served = call("GET", base + "/bin/install.sh")[2]
    prelude = served[:len(served) - len(install)]
    check(served.endswith(install) and prelude.startswith(b"#!/usr/bin/env bash\n")
          and ("\nexport CIDER_BUILD_HUB=https://%s:%d\n" % (DNS, port)).encode() in prelude and b"set --" not in prelude,
          "GET /bin/install.sh is install.sh unchanged after a prelude that exports this hub: %r" % prelude)
    check(subprocess.run(["bash", "-n"], input=served).returncode == 0, "the served install.sh parses with bash -n")

    for path, code_ in (("/workers/%s/admit?host=%s" % (LABEL, LABEL), 200), ("/workers/mac-off/admit", 403),
                        ("/workers/%s/admit" % HOSTNAME, 403), ("/workers/%s/admit?host=mac-off" % LABEL, 403)):
        code, text = answer("GET", path)
        check(code == code_ and (code == 200 or "Not touching anything on this Mac." in text),
              "GET %s answers %d: %s" % (path, code_, text.strip()))
    for label in ("mac-off", HOSTNAME):
        code, text = answer("PUT", "/workers/%s?slots=1" % label)
        check(code == 400, "PUT /workers/%s answers 400: %s" % (label, text.strip()))

    hub("PUT", "/workers/%s?slots=1&ram=32" % LABEL)
    beat([])
    check(LABEL in hub("GET", "/status"), "/status lists the Mac after its first heartbeat")

    first, second = submit("k1"), submit("k2")
    check(first[0] == "job" and second[0] == "job", "two different versions are queued as two jobs")
    for reply in (first, second):
        hub("PUT", "/source?job=" + reply[1], b"code")
    got = beat([])["jobs"]
    check(len(got) == 1, "a Mac with 1 slot receives one job (got %d)" % len(got))
    jid, attempt = got[0]["id"], got[0]["attempt"]
    beat([jid])

    q = urllib.parse.urlencode({"job": jid, "attempt": attempt, "label": LABEL, "rc": 0})
    check(hub("POST", "/w/result?" + q, ARTIFACT).split() == ["done"], "the Mac delivers its result and the job is done")
    check(hub("GET", "/poll?job=%s&waiter=cli1" % jid).split()[0] == "done", "a waiting client polls and sees done")
    check(len(beat([])["jobs"]) == 1, "once the slot frees up, the Mac receives the other job")

    done_key = "k1" if jid == first[1] else "k2"
    check(submit(done_key) == ["cached"], "the next request for the same version is answered from the cache")
    check(call("GET", base + "/cache/smoke/%s-ios.app.tar.gz" % done_key)[2] == ARTIFACT,
          "the client downloads the delivered artifact from /cache")

    hub("PUT", "/workers/mac-drained?slots=1&ram=32")
    third = submit("k3")
    hub("PUT", "/source?job=" + third[1], b"code")
    check(beat([], "mac-drained")["jobs"] == [] and json.loads(hub("GET", "/api/job?job=" + third[1]))["job"]["state"] == "queued",
          "a Mac that drain_command prints gets no job, and the job stays queued")
    drained = [w for w in json.loads(hub("GET", "/api/state"))["workers"] if w["label"] == "mac-drained"]
    check(drained and drained[0]["state"] == "drained" and drained[0]["state_text"] == "out of the pool",
          "/api/state shows it drained: %s" % drained)
    check(re.search(r"(?m)^mac-drained +out of the pool ", hub("GET", "/status")), "/status shows it out of the pool")

    rel = json.loads(hub("GET", "/api/state"))["release"]
    check(rel["source"] is None and rel["checked"] is None, "with no update_url, /api/state shows no update source")
    code, text = answer("POST", "/hub/check")
    check(code == 409 and "hub updates are off" in text, "POST /hub/check answers 409: %s" % text.strip())
    check(answer("POST", "/hub/update")[0] == 409, "POST /hub/update answers 409")
except (OSError, ValueError, KeyError, IndexError) as e:
    check(False, "unexpected error: %r" % e)
finally:
    proc.terminate()
    proc.wait()

print("hub log and CIDER_BUILD_HOME in %s" % tmp)
sys.exit(1 if failures else 0)
