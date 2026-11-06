#!/usr/bin/env python3
"""A stranger's client: `curl <hub>/bin/install.sh | bash -s client`, then `cider-build` with no CIDER_BUILD_HUB.

Starts the hub on 127.0.0.1 with an empty CIDER_BUILD_HOME (only its bin/) and a fake `tailscale` naming it
hubc.example.ts.net. A `curl` wrapper first on PATH sends https://<anything>.example.ts.net:<port> to the local hub
over plain HTTP, as MagicDNS and `tailscale serve` would. The client lives in temporary HOME, PREFIX and
XDG_CONFIG_HOME. A fake `ssh` and `scp` record where `cider-build add`, `remove` and `hub-install` would go and what
they would run. Touches no network. Exits 0 if every check passes.
"""
import getpass
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DNS = "hubc.example.ts.net"
tmp = tempfile.mkdtemp(prefix="cider-build-client-")
home, fakebin, log = (os.path.join(tmp, d) for d in ("hub", "fakebin", "log"))
for d in (os.path.join(home, "bin"), fakebin, log):
    os.makedirs(d)
for f in ("install.sh", "bin/cider-build"):
    shutil.copy(os.path.join(REPO, f), os.path.join(home, "bin", os.path.basename(f)))

failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fake(name, body):
    with open(os.path.join(fakebin, name), "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(os.path.join(fakebin, name), 0o755)


port = free_port()
local = "http://127.0.0.1:%d" % port
canonical = "https://%s:%d" % (DNS, port)
fake("tailscale", "echo '%s'" % json.dumps({"BackendState": "Running", "Self": {
    "TailscaleIPs": ["127.0.0.1"], "DNSName": DNS + ".", "HostName": "hubc"}}))
fake("curl", 'exec %s "${@//https:\\/\\/*.example.ts.net:%d/%s}"' % (shutil.which("curl"), port, local))
# ssh: the target is the first argument after the -o pairs; what rsh runs arrives on stdin.
fake("ssh", 'while [ "$1" = -o ]; do shift 2; done\n'
            'n=$(ls %s/*.target 2>/dev/null | wc -l); echo "$1" > %s/$n.target; cat > %s/$n.script; printf "\\n__rc=0\\n"'
            % (log, log, log))
fake("scp", 'echo "$@" > %s/scp.args' % log)


def calls():
    out = []
    for n in range(len([f for f in os.listdir(log) if f.endswith(".target")])):
        with open(os.path.join(log, "%d.target" % n)) as t, open(os.path.join(log, "%d.script" % n)) as s:
            out.append((t.read().strip(), s.read()))
    shutil.rmtree(log)
    os.makedirs(log)
    return out


def client(name, *args, env=None, shell=None):
    """Runs cider-build (or a shell line) as the client `name`, with its own HOME, PREFIX and XDG_CONFIG_HOME."""
    root = os.path.join(tmp, name)
    e = {k: v for k, v in os.environ.items() if k not in ("CIDER_BUILD_HUB", "MAC_BUILD_HUB")}
    e.update(HOME=os.path.join(root, "home"), PREFIX=os.path.join(root, "bin"), XDG_CONFIG_HOME=os.path.join(root, "xdg"),
             PATH="%s:%s:%s" % (fakebin, os.path.join(root, "bin"), os.environ["PATH"]))
    e.update(env or {})
    os.makedirs(e["HOME"], exist_ok=True)
    cmd = ["bash", "-c", shell] if shell else [os.path.join(root, "bin", "cider-build")] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=e["HOME"], timeout=60)
    return r.returncode, r.stdout + r.stderr


def saved(name):
    try:
        with open(os.path.join(tmp, name, "xdg", "cider-build", "hub")) as f:
            return f.read()
    except OSError:
        return None


proc = subprocess.Popen([sys.executable, os.path.join(REPO, "bin", "cider-build-hub")],
                        env=dict(os.environ, CIDER_BUILD_HOME=home, CIDER_BUILD_PORT=str(port),
                                 CIDER_BUILD_TAILNET_PORT=str(free_port()), PATH=fakebin + ":/usr/bin:/bin"),
                        stderr=open(os.path.join(tmp, "hub.log"), "w"))
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(local + "/bin/install.sh", timeout=5).read()
            break
        except OSError:
            time.sleep(0.1)

    rc, out = client("stranger", shell="curl -fsSL %s/bin/install.sh | bash -s client" % canonical)
    check(rc == 0 and saved("stranger") == canonical + "\n",
          "curl <hub>/bin/install.sh | bash -s client saves the hub that served it (rc=%d): %s" % (rc, out.strip()[-300:]))
    check("MAC " in out and "Done." in out, "and ends with the hub's status and Done")
    check("npx skills add dtowers10/cider-builder --skill cider-build -g" in out
          and os.path.isfile(os.path.join(REPO, "skills", "cider-build", "SKILL.md")),
          "and names the agent skill that this repository ships")
    rc, out = client("stranger", "hub")
    check(rc == 0 and out.startswith(canonical + "\n") and "(saved in %s/stranger/xdg/cider-build/hub)" % tmp in out,
          "cider-build hub prints it and where it is saved: %s" % out.strip())
    rc, out = client("stranger", "status")
    check(rc == 0 and out.startswith("MAC "), "cider-build status works with no CIDER_BUILD_HUB in the environment")
    rc, out = client("stranger", "hub", env={"CIDER_BUILD_HUB": local})
    check(rc == 0 and out.startswith(local + "\n") and "(from CIDER_BUILD_HUB)" in out, "CIDER_BUILD_HUB overrides the saved hub")

    rc, out = client("other", shell="curl -fsSL %s/bin/install.sh | bash -s client --hub %s/" % (local, local))
    check(rc == 0 and saved("other") == local + "\n", "--hub overrides the hub that served the script: %r" % saved("other"))
    rc, out = client("other", "status", env={"PATH": "%s:/usr/bin:/bin" % os.path.join(tmp, "other", "bin")})
    check(rc == 0 and out.startswith("MAC "), "and cider-build status reaches it with the real curl")

    # A client from before the rename to Cider Builder: mac-build in PREFIX and its hub saved under its old name.
    old = os.path.join(tmp, "legacy")
    os.makedirs(os.path.join(old, "bin"))
    os.makedirs(os.path.join(old, "xdg", "mac-build"))
    with open(os.path.join(old, "bin", "mac-build"), "w") as f:
        f.write("#!/bin/sh\necho old mac-build\n")
    with open(os.path.join(old, "xdg", "mac-build", "hub"), "w") as f:
        f.write(local + "\n")
    shutil.copy(os.path.join(REPO, "bin", "cider-build"), os.path.join(old, "bin", "cider-build"))
    rc, out = client("legacy", "hub")
    check(rc == 0 and out.startswith(local + "\n") and "(saved in %s/xdg/mac-build/hub)" % old in out,
          "cider-build reads the hub mac-build saved: %s" % out.strip())
    rc, out = client("legacy", "hub", env={"MAC_BUILD_HUB": canonical})
    check(rc == 0 and out.startswith(canonical + "\n") and "(from MAC_BUILD_HUB)" in out, "and MAC_BUILD_HUB: %s" % out.strip())
    rc, out = client("legacy", "hub", env={"MAC_BUILD_HUB": canonical, "CIDER_BUILD_HUB": local})
    check(rc == 0 and out.startswith(local + "\n") and "(from CIDER_BUILD_HUB)" in out, "CIDER_BUILD_HUB wins over MAC_BUILD_HUB")
    rc, out = client("legacy", shell="curl -fsSL %s/bin/install.sh | bash -s client" % canonical)
    check(rc == 0 and os.readlink(os.path.join(old, "bin", "mac-build")) == "cider-build",
          "installing over mac-build turns it into a link to cider-build (rc=%d): %s" % (rc, out.strip()[-300:]))
    rc, out = client("legacy", "status", shell="mac-build status")
    check(rc == 0 and out.startswith("MAC "), "so mac-build status still works: %s" % out.strip()[:200])
    check(all(urllib.request.urlopen(local + "/bin/" + old_name, timeout=5).read()
              == urllib.request.urlopen(local + "/bin/" + new_name, timeout=5).read()
              for old_name, new_name in (("mac-build", "cider-build"), ("install.sh", "install.sh"))),
          "the hub serves /bin/mac-build as cider-build, for anything that still fetches the old name")

    os.makedirs(os.path.join(tmp, "nohub", "bin"))
    shutil.copy(os.path.join(REPO, "bin", "cider-build"), os.path.join(tmp, "nohub", "bin", "cider-build"))
    for args in (["ios"], ["status"], ["add", "mac-x"], ["hub"]):
        rc, out = client("nohub", *args)
        check(rc == 2 and "Install it from your hub" in out and "/bin/install.sh | bash -s client" in out,
              "with no hub, cider-build %s exits 2 and says how to install from the hub" % " ".join(args))
    rc, out = client("nohub", "hub", "buildhub:4710")
    check(rc == 2 and saved("nohub") is None, "cider-build hub refuses something that is not a URL")
    rc, out = client("nohub", shell="bash %s client" % os.path.join(REPO, "install.sh"))
    check(rc == 0 and "cider-build does not know its hub yet" in out and saved("nohub") is None,
          "install.sh client from a clone with no hub installs and says how to name one")

    calls()
    rc, out = client("stranger", "add", "mac-x")
    got = calls()
    check(rc == 0 and [t for t, _ in got] == ["root@mac-x.example.ts.net"],
          "cider-build add mac-x goes to root@mac-x on the hub's tailnet domain: %s" % [t for t, _ in got])
    check("curl -fsSL %s/join | bash -s --" % canonical in got[0][1], "and runs the hub's /join there")
    rc, out = client("stranger", "add", "mac-x", "2", "--user", "ci builder")
    got = calls()
    check(rc == 0 and "--slots 2 --user ci\\ builder" in got[0][1], "add passes slots and --user through: %r" % got[0][1].strip())
    rc, out = client("stranger", "add", "mac-x.other.net")
    check([t for t, _ in calls()] == ["root@mac-x.other.net"], "a Mac name with a dot is used as typed")
    rc, out = client("stranger", "add", "mac-x", env={"CIDER_BUILD_HUB": local})
    check([t for t, _ in calls()] == ["root@mac-x"], "with a hub URL by IP, the Mac's short name")
    hub_beat = {"label": "mac-y", "boot": "b", "running": [], "tools_ready": True}
    urllib.request.urlopen(urllib.request.Request(local + "/w/heartbeat", json.dumps(hub_beat).encode(), method="POST")).read()
    urllib.request.urlopen(urllib.request.Request(local + "/workers/mac-y?slots=1", method="PUT")).read()
    rc, out = client("stranger", "remove", "mac-y.example.ts.net")
    got = calls()
    state = json.loads(urllib.request.urlopen(local + "/api/state").read())
    check(rc == 0 and [t for t, _ in got] == ["root@mac-y.example.ts.net"] and "| bash -s -- worker --remove" in got[0][1]
          and not next(w for w in state["workers"] if w["label"] == "mac-y")["enabled"],
          "remove disables mac-y on the hub first, then runs install.sh --remove on it")

    def checkout(name, origin=None):
        """A copy of install.sh and bin/ as a client would have it; with origin, a git clone on branch work tracking
        origin's stable."""
        d = os.path.join(tmp, name)
        os.makedirs(d)
        shutil.copy(os.path.join(REPO, "install.sh"), d)
        shutil.copytree(os.path.join(REPO, "bin"), os.path.join(d, "bin"))
        if origin:
            for args in (["init", "-q", "-b", "work"], ["remote", "add", "origin", origin],
                         ["config", "branch.work.remote", "origin"], ["config", "branch.work.merge", "refs/heads/stable"]):
                subprocess.run(["git", "-C", d] + args, check=True, capture_output=True)
        return d

    def install_args(script):
        line = next(l for l in script.splitlines() if "install.sh hub" in l)
        return shlex.split(line.split("install.sh hub", 1)[1].split(";", 1)[0])

    clone = checkout("clone", "https://me:t0ken@git.example.com/me/cider-builder.git")
    rc, out = client("stranger", env={"CIDER_BUILD_HUB": local}, shell="%s/bin/cider-build hub-install --set exclude=mac-z" % clone)
    scp = open(os.path.join(log, "scp.args")).read().split() if os.path.exists(os.path.join(log, "scp.args")) else []
    got = calls()
    user = getpass.getuser()
    check(rc == 0 and [t for t, _ in got] == ["%s@127.0.0.1" % user, "root@127.0.0.1"],
          "hub-install asks the hub which user runs it: %s (rc=%d %s)" % ([t for t, _ in got], rc, out.strip()[-200:]))
    check(scp[-3:] == [os.path.join(clone, "install.sh"), os.path.join(clone, "bin"), "%s@127.0.0.1:/tmp/cider-build-install/" % user]
          and "-r" in scp, "it sends install.sh and bin/ whole: %s" % scp)
    check(install_args(got[1][1]) == ["--user", user, "--source", "https://me:t0ken@git.example.com/me/cider-builder.git",
                                      "stable", "--set", "exclude=mac-z"],
          "and runs install.sh hub as root with the clone's remote and branch as --source, then its options: %r"
          % got[1][1].strip())
    check("t0ken" not in out, "hub-install prints no token")
    rc, out = client("nohub", shell="%s/bin/cider-build hub-install ops@buildhub.example.ts.net" % checkout("plain"))
    got = calls()
    check(rc == 0 and [t for t, _ in got] == ["ops@buildhub.example.ts.net", "root@buildhub.example.ts.net"]
          and install_args(got[1][1]) == ["--user", "ops"],
          "hub-install user@host from a copy with no git needs no hub and passes no --source: %r" % got[1][1].strip())
    rc, out = client("nohub", shell="%s/bin/cider-build hub-install ops@buildhub.example.ts.net" % checkout("local", "/srv/cider-builder.git"))
    got = calls()
    check(rc == 0 and install_args(got[1][1]) == ["--user", "ops"], "a remote that is a path on the client is not passed")
except (OSError, ValueError, KeyError, IndexError, StopIteration, subprocess.SubprocessError) as e:
    check(False, "unexpected error: %r" % e)
finally:
    proc.terminate()
    proc.wait()

print("hub log and clients in %s" % tmp)
sys.exit(1 if failures else 0)
