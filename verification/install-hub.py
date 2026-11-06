#!/usr/bin/env python3
"""`install.sh hub` on Linux, with fakes for the macOS tools, and where the hub updates itself from.

Runs this checkout's install.sh from a scratch git clone and from a plain copy, as a fake root, into a temporary
home. A fake launchctl starts the hub from the plist it was given, so each install ends with a real hub on
127.0.0.1. update_check_s=0 keeps the hub from fetching, and a fake ssh refuses everything: touches no network.
Checks: the clone's remote and branch become update_url and update_branch on a hub that never chose one; an ssh
remote gets the deploy key, created once and reused; update_url=off survives reinstalls; --set update_url wins;
a plain copy stays off unless given --source; a token in a URL is never printed; a mac-build hub from before the
rename moves to ~/cider-build with its state and deploy key. Exits 0 if every check passes.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = tempfile.mkdtemp(prefix="cider-build-install-hub-")
CLONE, COPY, FAKE, LD = (os.path.join(SIM, d) for d in ("clone", "copy", "fake", "LaunchDaemons"))
for d in (FAKE, LD):
    os.makedirs(d)
HTTPS = "https://me:t0ken@git.example.com/me/cider-builder.git"
SSH = "me@git.example.com:me/cider-builder.git"

with open(os.path.join(REPO, "install.sh")) as f:
    script = f.read()
for old, new in (("/Library/LaunchDaemons", LD), ("DAEMON_PATH=/opt/homebrew/bin:", "DAEMON_PATH=%s:/opt/homebrew/bin:" % FAKE)):
    assert old in script, old
    script = script.replace(old, new)
for d in (CLONE, COPY):
    shutil.copytree(os.path.join(REPO, "bin"), os.path.join(d, "bin"))
    with open(os.path.join(d, "install.sh"), "w") as f:
        f.write(script)


def git(*args):
    return subprocess.run(["git", "-C", CLONE] + list(args), check=True, capture_output=True, text=True).stdout.strip()


git("init", "-q", "-b", "work")
git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "scratch")
git("remote", "add", "origin", HTTPS)
git("config", "branch.work.remote", "origin")
git("config", "branch.work.merge", "refs/heads/stable")

LAUNCHD = '''import os, plistlib, signal, subprocess, sys, time
pidfile = os.path.join(%r, "hub.pid")
if os.path.exists(pidfile):
    try:
        os.kill(int(open(pidfile).read()), signal.SIGTERM)
        time.sleep(0.5)
    except (OSError, ValueError):
        pass
    os.unlink(pidfile)
if sys.argv[1] == "start":
    p = plistlib.load(open(sys.argv[2], "rb"))
    log = open(p["StandardErrorPath"], "a")
    proc = subprocess.Popen(p["ProgramArguments"], env=p["EnvironmentVariables"], cwd=p["WorkingDirectory"],
                            stdout=log, stderr=log, start_new_session=True)
    open(pidfile, "w").write(str(proc.pid))
''' % SIM
with open(os.path.join(SIM, "launchd.py"), "w") as f:
    f.write(LAUNCHD)
FAKES = {
    "uname": 'echo Darwin',
    "id": 'case "$*" in "-u") echo 0 ;; "-un") echo root ;; -u\\ *) echo 1000 ;; *) exit 0 ;; esac',
    "dscl": 'echo "NFSHomeDirectory: $SIM_HOME"',
    "sudo": 'while [ $# -gt 0 ]; do case $1 in -u) shift 2 ;; -H) shift ;; *) break ;; esac; done; exec "$@"',
    "chown": 'exit 0',
    "stat": 'if [ "$1" = -f ]; then whoami; else exec /usr/bin/stat "$@"; fi',
    "ssh": 'echo "fake ssh: no network in this test" >&2; exit 255',
    "tailscale": '''case "$1" in
  status) echo '{"BackendState": "Running", "Self": {"TailscaleIPs": ["127.0.0.1"], "DNSName": "buildhub.example.ts.net.", "HostName": "buildhub"}}' ;;
  serve) [ "$2" != status ] || echo '{}' ;;
  ip) echo 127.0.0.1 ;;
esac''',
    "launchctl": 'case "$1" in bootstrap) exec python3 %s/launchd.py start "$3" ;; bootout) exec python3 %s/launchd.py stop ;; esac'
                 % (SIM, SIM),
}
for name, body in FAKES.items():
    with open(os.path.join(FAKE, name), "w") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(os.path.join(FAKE, name), 0o755)

failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


def free_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


class Hub:
    def __init__(self, name):
        self.home = os.path.join(SIM, name)
        self.B = os.path.join(self.home, "cider-build")
        self.key = os.path.join(self.home, ".ssh", "cider-build-deploy")
        self.port, self.first = free_port(), True
        os.makedirs(self.home)

    def install(self, where, *args):
        """install.sh hub from `where` (CLONE, COPY or "hub": the hub's own bin/); returns (rc, everything printed)."""
        sh = os.path.join(self.B, "bin", "install.sh") if where == "hub" else os.path.join(where, "install.sh")
        if self.first:
            args = ("--set", "port=%d" % self.port, "--set", "tailnet_port=%d" % free_port(), "--set", "update_check_s=0") + args
            self.first = False
        env = dict(os.environ, PATH=FAKE + ":/usr/bin:/bin", SIM_HOME=self.home, HOME=self.home)
        r = subprocess.run(["bash", sh, "hub", "--user", "builds"] + list(args), capture_output=True, text=True,
                           env=env, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def settings(self):
        with open(os.path.join(self.B, "hub.json")) as f:
            return json.load(f)

    def source(self):
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/api/state" % self.port, timeout=5).read())
        return st["release"]["source"]


def no_token(out, what):
    check("t0ken" not in out, "%s: the token in the URL is never printed" % what)


try:
    a = Hub("a")
    rc, out = a.install(CLONE)
    s = a.settings()
    check(rc == 0 and s.get("update_url") == HTTPS and s.get("update_branch") == "stable" and "update_ssh_key" not in s,
          "first install from a clone records its https remote and the branch HEAD tracks, with no key: %s (rc=%d %s)"
          % ({k: v for k, v in s.items() if k.startswith("update")}, rc, out.strip()[-300:]))
    check(not os.path.exists(a.key), "an https source creates no deploy key")
    check("Hub updates: from https://git.example.com/me/cider-builder.git, branch stable" in out
          and "--set update_url=off" in out, "the summary names the source, redacted, and how to turn updates off")
    no_token(out, "first install")
    check(a.source() == {"url": "https://git.example.com/me/cider-builder.git", "branch": "stable", "check_s": 0},
          "the running hub has that source, redacted: %s" % a.source())

    git("remote", "set-url", "origin", SSH)
    rc, out = a.install(CLONE)
    check(rc == 0 and a.settings()["update_url"] == HTTPS and not os.path.exists(a.key),
          "a reinstall keeps the recorded source though the clone's remote changed")
    no_token(out, "reinstall")

    rc, out = a.install("hub", "--set", "update_url=off")
    check(rc == 0 and a.settings()["update_url"] == "off" and "Hub updates: off" in out and a.source() is None,
          "--set update_url=off turns updates off: %s" % a.source())
    rc, out = a.install(CLONE)
    check(rc == 0 and a.settings()["update_url"] == "off" and a.source() is None,
          "update_url=off survives a reinstall from a clone")
    rc, out = a.install(COPY, "--source", HTTPS, "main")
    check(rc == 0 and a.settings()["update_url"] == "off", "and a reinstall with --source (what hub-install passes)")
    no_token(out, "--source on an off hub")

    rc, out = a.install("hub", "--set", "update_url=")
    check(rc == 0 and "update_url" not in a.settings() and "Hub updates: off" in out,
          "--set update_url= forgets the decision and, from the hub's own copy, leaves updates off")
    rc, out = a.install(CLONE)
    s = a.settings()
    check(rc == 0 and s["update_url"] == SSH and s["update_branch"] == "stable" and s.get("update_ssh_key") == a.key,
          "with no decision, a reinstall from the clone records its ssh remote and the deploy key: %s" % s)
    check(os.path.exists(a.key) and open(a.key + ".pub").read().strip() in out, "it creates the key and prints its public half")
    mtime = os.path.getmtime(a.key)
    a.install("hub", "--set", "update_url=", "--set", "update_ssh_key=")
    rc, out = a.install(CLONE)
    check(rc == 0 and a.settings().get("update_ssh_key") == a.key and os.path.getmtime(a.key) == mtime,
          "the next time an ssh source is recorded, the existing key is reused, not regenerated")

    a.install("hub", "--set", "update_url=", "--set", "update_branch=")
    rc, out = a.install(CLONE, "--set", "update_url=https://other.example.com/fork.git")
    s = a.settings()
    check(rc == 0 and s["update_url"] == "https://other.example.com/fork.git" and "update_branch" not in s,
          "--set update_url wins over the clone's remote, which brings no branch then: %s" % s)
    rc, out = a.install(CLONE, "--set", "update_url=https://me:t0ken@other.example.com/fork.git")
    check(rc == 0 and a.settings()["update_url"] == "https://me:t0ken@other.example.com/fork.git",
          "--set update_url also replaces a recorded source")
    no_token(out, "--set with a token")
    rc, out = a.install(CLONE, "--set", "update_url=-oProxyCommand=https://me:t0ken@x")
    check(rc == 2 and "update_url" in out and a.settings()["update_url"] == "https://me:t0ken@other.example.com/fork.git",
          "a refused update_url exits 2 and changes nothing: %s" % out.strip().splitlines()[-2:])
    no_token(out, "a refused --set")

    b = Hub("b")
    rc, out = b.install(COPY)
    check(rc == 0 and "update_url" not in b.settings() and b.source() is None,
          "a plain copy (no git) with no --source leaves updates off: %s" % b.settings())
    check("Hub updates: off" in out and "install.sh hub --set update_url=<git URL>" in out,
          "and the summary says how to turn them on")
    rc, out = b.install(COPY, "--source", HTTPS, "release")
    check(rc == 0 and b.settings().get("update_url") == HTTPS and b.settings().get("update_branch") == "release",
          "a plain copy with --source URL BRANCH records them on a hub with no decision")
    no_token(out, "--source")
    rc, out = b.install(COPY, "--source", HTTPS)
    check(rc == 2 and "--source needs" in out, "--source needs both a URL and a branch")

    # A mac-build hub from before the rename to Cider Builder: its LaunchDaemon, its ~/mac-build with old program
    # names, a rollback copy, a cached artifact, and an ssh source whose deploy key has the old name.
    m = Hub("m")
    old = os.path.join(m.home, "mac-build")
    for d in ("bin/.previous", "cache/MyApp", ".ssh"):
        os.makedirs(os.path.join(m.home, ".ssh" if d == ".ssh" else os.path.join("mac-build", d)), exist_ok=True)
    for f in ("bin/mac-build", "bin/mac-build-hub", "bin/mac-build-worker", "bin/mac-build-panel.html",
              "bin/.previous/mac-build-hub", "cache/MyApp/k-android.apk"):
        with open(os.path.join(old, f), "w") as fh:
            fh.write("old\n")
    with open(os.path.join(old, "hub.json"), "w") as fh:
        json.dump({"port": m.port, "tailnet_port": free_port(), "update_check_s": 0, "update_url": SSH}, fh)
    old_key = os.path.join(m.home, ".ssh", "mac-build-deploy")
    for f in (old_key, old_key + ".pub"):
        with open(f, "w") as fh:
            fh.write("ssh-ed25519 OLDKEY mac-build hub\n")
    old_plist = os.path.join(LD, "com.mac-build.hub.plist")
    with open(old_plist, "w") as fh:
        fh.write("<plist/>\n")
    m.first = False
    rc, out = m.install(COPY)
    check(rc == 0 and not os.path.exists(old) and not os.path.exists(old_plist)
          and os.path.exists(os.path.join(LD, "com.cider-build.hub.plist")),
          "a mac-build hub: its plist is gone and ~/mac-build moved to ~/cider-build (rc=%d %s)" % (rc, out.strip()[-300:]))
    check(os.path.exists(os.path.join(m.B, "cache", "MyApp", "k-android.apk")) and m.settings().get("update_url") == SSH,
          "its cache and hub.json come along: %s" % m.settings())
    check(not any(os.path.exists(os.path.join(m.B, "bin", f)) for f in
                  ("mac-build", "mac-build-hub", "mac-build-worker", "mac-build-panel.html", ".previous"))
          and os.path.exists(os.path.join(m.B, "bin", "cider-build-hub")),
          "its programs under the old names and the rollback copy are gone: %s" % sorted(os.listdir(os.path.join(m.B, "bin"))))
    check(m.settings().get("update_ssh_key") == old_key and not os.path.exists(m.key) and "OLDKEY" in out,
          "an ssh source keeps the deploy key the git host already accepts: %s" % m.settings().get("update_ssh_key"))
    check(m.source() is not None, "and the hub runs on the same port")
except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
    check(False, "unexpected error: %r" % e)
finally:
    subprocess.run(["python3", os.path.join(SIM, "launchd.py"), "stop"])
    print("scratch files in %s" % SIM)
sys.exit(1 if failures else 0)
