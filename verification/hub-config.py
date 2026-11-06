#!/usr/bin/env python3
"""The hub's settings: $CIDER_BUILD_HOME/hub.json, the env overrides and `cider-build-hub config`.

Loads bin/cider-build-hub as a module on a temporary CIDER_BUILD_HOME and runs its `config` command as a subprocess.
Touches no network. Exits 0 if every check passes.
"""
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB_PY = os.path.join(REPO, "bin", "cider-build-hub")
tmp = tempfile.mkdtemp(prefix="cider-build-config-")
os.environ["CIDER_BUILD_HOME"] = os.path.join(tmp, "module")
HUB = importlib.machinery.SourceFileLoader("hub", HUB_PY).load_module()

failures = 0


def check(ok, what):
    global failures
    print("%s  %s" % ("OK  " if ok else "FAIL", what))
    failures += not ok


def config(raw, environ=None):
    return HUB.load_config(raw, environ or {})


def refused(raw, environ=None):
    try:
        config(raw, environ)
    except HUB.ConfigError as e:
        return str(e)
    return None


def cli(home, *args, env=None):
    r = subprocess.run([sys.executable, HUB_PY, "config"] + list(args), capture_output=True, text=True,
                       env=dict(os.environ, CIDER_BUILD_HOME=home, **(env or {})))
    return r.returncode, r.stdout, r.stderr


c = HUB.CONFIG
check(c.update_url is None and c.port == 4710 and c.tailnet_port == 4711 and c.exclude == frozenset()
      and c.drain_command is None and c.update_branch == "main" and set(c.origin.values()) == {"default"},
      "with no hub.json every setting is its default, and hub updates are off")

c = config({"port": 4800, "update_url": "https://git.example.com/me/repo.git", "exclude": ["mac-a", "mac-b"],
            "drain_command": "/usr/local/bin/macs-out", "cache_keep": "3"})
check(c.port == 4800 and c.update_url == "https://git.example.com/me/repo.git" and c.exclude == {"mac-a", "mac-b"}
      and c.drain_command == "/usr/local/bin/macs-out" and c.cache_keep == 3 and c.origin["port"] == "hub.json",
      "values come from hub.json")
c = config({"port": 4800, "update_branch": "stable"}, {"CIDER_BUILD_PORT": "4900", "CIDER_BUILD_BRANCH": ""})
check(c.port == 4900 and c.origin["port"] == "env CIDER_BUILD_PORT", "the environment beats hub.json")
check(c.update_branch == "main" and c.origin["update_branch"] == "env CIDER_BUILD_BRANCH",
      "an empty env value means the default, even over hub.json")
check(config({"update_url": None, "exclude": ""}).update_url is None, "null or an empty value in hub.json is the default")
check(config({}, {"CIDER_BUILD_REPO": "/srv/repo.git", "CIDER_BUILD_EXCLUDE": "mac-a, mac-b"}).update_url == "/srv/repo.git"
      and config({}, {"CIDER_BUILD_EXCLUDE": "mac-a, mac-b"}).exclude == {"mac-a", "mac-b"},
      "CIDER_BUILD_REPO sets update_url, and an exclude list in env splits on commas and spaces")
c = config({"port": 4800}, {"MAC_BUILD_PORT": "4901", "MAC_BUILD_CACHE_KEEP": "7", "CIDER_BUILD_CACHE_KEEP": "8"})
check(c.port == 4901 and c.origin["port"] == "env MAC_BUILD_PORT" and c.cache_keep == 8
      and c.origin["cache_keep"] == "env CIDER_BUILD_CACHE_KEEP",
      "a MAC_BUILD_* variable from before the rename still works, and the CIDER_BUILD_* one wins")
c = config({}, {"MAC_BUILD_REPO": "/srv/old.git", "CIDER_BUILD_REPO": ""})
check(c.update_url is None and c.origin["update_url"] == "env CIDER_BUILD_REPO",
      "an empty CIDER_BUILD_* variable also wins, as smoke() needs")

for raw, key in (({"port": "x"}, "port"), ({"port": 70000}, "port"), ({"port": True}, "port"),
                 ({"update_url": "-oProxyCommand=touch /tmp/pwned"}, "update_url"), ({"exclude": 5}, "exclude"),
                 ({"exclude": ["ok", "bad name"]}, "exclude"), ({"update_branch": "../x"}, "update_branch"),
                 ({"update_ssh_key": "relative/key"}, "update_ssh_key"), ({"drain_command": "a\nb"}, "drain_command"),
                 ({"cache_keep": 0}, "cache_keep"), ({"cache_prune_s": 4}, "cache_prune_s")):
    why = refused(raw)
    check(why is not None and why.startswith("hub.json: %s: " % key), "%s is refused: %s" % (json.dumps(raw), why))
why = refused({"port": "x"}, {"CIDER_BUILD_PORT": "4900"})
check(why is not None and why.startswith("hub.json: port:"), "a bad hub.json value is refused even when env overrides it")
why = refused({}, {"CIDER_BUILD_TAILNET_PORT": "0"})
check(why is not None and why.startswith("env CIDER_BUILD_TAILNET_PORT: tailnet_port:"), "a bad env value names the variable: %s" % why)
c = config({"colour": "blue"})
check(c.warnings == ("hub.json: unknown setting 'colour' (ignored)",), "an unknown key is a warning, not an error")
check(config({"update_ssh_key": "~/.ssh/k"}).update_ssh_key == os.path.expanduser("~/.ssh/k"), "update_ssh_key expands ~")

check(HUB.redact("https://me:t0ken@git.example.com/x.git") == "https://git.example.com/x.git"
      and HUB.redact("fatal: unable to access 'https://t0ken@git.example.com/x.git/': 403") ==
      "fatal: unable to access 'https://git.example.com/x.git/': 403", "redact() drops user:token@ from URLs in text")
check(HUB.redact("me@git.example.com:x/y.git") == "me@git.example.com:x/y.git" and HUB.redact("/srv/x.git") == "/srv/x.git",
      "redact() leaves scp-like URLs and paths alone")

check(config({"update_url": "off"}).update_url == "off" and config({}, {"CIDER_BUILD_REPO": " OFF "}).update_url == "off",
      "update_url=off is a value of its own, any case, in hub.json or env")
for raw in ({"update_url": "off"}, {}):
    HUB.CONFIG = config(raw)
    try:
        HUB.start_release("checking", lambda: None)
        why = None
    except HUB.HttpError as e:
        why = (e.code, str(e))
    check(HUB.update_source() is None and why and why[0] == 409,
          "with update_url %s the hub has no update source and refuses a check: %s" % (raw.get("update_url", "unset"), why))
HUB.CONFIG = config({"update_url": "https://git.example.com/me/repo.git"})
check(HUB.update_source() == "https://git.example.com/me/repo.git", "any other update_url is the update source")

HUB.CONFIG = config({"exclude": ["my-laptop"]})
HUB.hub_url["label"] = "buildhub"
check(HUB.refusal("buildhub") == "buildhub is the hub: the hub coordinates and does not build.",
      "refusal() turns away the hub's own tailnet name, with no configuration")
check("exclude list" in (HUB.refusal("other", "my-laptop") or ""), "refusal() turns away a Mac in exclude by any of its names")
check(HUB.refusal("mac-mini-2", "") is None, "refusal() lets any other Mac build")

home = os.path.join(tmp, "cli")
path = os.path.join(home, "hub.json")
rc, out, _ = cli(home)
check(rc == 0 and "absent" in out and all(s.key in out for s in HUB.SETTINGS), "`config` with no file lists every setting")
rc, _, err = cli(home, "set", "exclude=mac-a,mac-b", "update_url=/srv/repo.git", "port=4800")
check(rc == 0 and json.load(open(path)) == {"exclude": ["mac-a", "mac-b"], "update_url": "/srv/repo.git", "port": 4800},
      "`config set` writes the parsed values: %s" % (err.strip() or open(path).read().strip()))
check(os.stat(path).st_mode & 0o777 == 0o600, "hub.json is mode 0600 (update_url may hold a token)")
check(cli(home, "get", "exclude")[1] == "mac-a,mac-b\n" and cli(home, "get", "drain_command")[1] == "\n",
      "`config get` prints a list comma-separated and an unset value as an empty line")
rc, out, _ = cli(home, env={"CIDER_BUILD_PORT": "4900"})
check(rc == 0 and any(l.split()[:3] == ["port", "4900", "env"] for l in out.splitlines()), "`config` shows where a value comes from")

with open(path) as f:
    data = json.load(f)
data["colour"] = "blue"
with open(path, "w") as f:
    json.dump(data, f)
before = open(path, "rb").read()
for args, why in ((["set", "port=99999"], "a bad value"), (["set", "port=4801", "colur=x"], "an unknown key"),
                  (["set", "port"], "no ="), (["set", "update_url=-x", "port=4801"], "one bad value among good ones")):
    rc, _, err = cli(home, *args)
    check(rc != 0 and open(path, "rb").read() == before, "`config %s` (%s) fails and leaves hub.json byte-identical: %s"
          % (" ".join(args), why, err.strip()))
rc, _, _ = cli(home, "set", "update_url=Off")
check(rc == 0 and json.load(open(path))["update_url"] == "off" and cli(home, "get", "update_url")[1] == "off\n",
      "`config set update_url=Off` saves off, and `config get` tells it apart from unset")
rc, _, _ = cli(home, "set", "update_url=https://me:t0ken@git.example.com/me/repo.git")
rc, out, _ = cli(home)
check(rc == 0 and "t0ken" not in out and "https://git.example.com/me/repo.git" in out,
      "the `config` listing redacts a token in update_url")
check(cli(home, "get", "update_url")[1] == "https://me:t0ken@git.example.com/me/repo.git\n", "`config get` prints it whole")
rc, out, _ = cli(home, "set", "update_url=")
check(rc == 0 and "update_url" not in json.load(open(path)) and json.load(open(path))["colour"] == "blue",
      "`config set KEY=` removes the key and keeps keys this hub does not know")
rc, out, _ = cli(home)
check(rc == 0 and "unknown setting 'colour'" in out, "`config` prints the warnings")

with open(path, "w") as f:
    json.dump({"port": "x"}, f)
rc, _, err = cli(home)
check(rc == 1 and err.strip() == "hub.json: port: not a whole number: 'x'", "`config` exits 1 with the reason: %s" % err.strip())
rc, _, err = cli(home, "set", "port=4802")
check(rc == 0 and json.load(open(path)) == {"port": 4802}, "`config set` repairs the bad value that stops the hub")
with open(path, "w") as f:
    json.dump({"exclude": "bad name!"}, f)
r = subprocess.run([sys.executable, HUB_PY], capture_output=True, text=True, timeout=20, env=dict(os.environ, CIDER_BUILD_HOME=home))
check(r.returncode == 78 and r.stderr == "cider-build-hub cannot start: hub.json: exclude: not a Mac name: 'name!'\n",
      "the hub does not start on an invalid hub.json: exit %d, %r" % (r.returncode, r.stderr))

with open(os.path.join(REPO, "docs", "configuration.md")) as f:
    doc = f.read()
missing = [s.key for s in HUB.SETTINGS if "\n| `%s` |" % s.key not in doc or s.env not in doc]
check(not missing, "docs/configuration.md's table and env list cover every setting (missing: %s)" % missing)

print("scratch files in %s" % tmp)
sys.exit(1 if failures else 0)
