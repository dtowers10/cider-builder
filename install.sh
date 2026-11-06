#!/usr/bin/env bash
# Installs or updates Cider Builder. Safe to repeat: leaves everything as is if already installed.
#
#   ./install.sh hub [--user U] [--set KEY=VALUE]... [--source URL BRANCH]
#       On the Mac that acts as the hub, as the user that will run the server (asks for sudo), or as
#       root with --user. Installs cider-build-hub as a LaunchDaemon (starts with the Mac, no login
#       session needed) and publishes it on the tailnet with `tailscale serve` (https://<hub>:4710).
#       Keeps its state in ~/cider-build and its settings in ~/cider-build/hub.json. --set changes one
#       setting (an empty VALUE puts back the default) and the others keep their value. On the hub,
#       without a clone: bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>
#       The hub updates itself from the repository it was installed from: the clone's remote and branch,
#       or --source (what `cider-build hub-install` passes). Only while update_url is unset: a URL set
#       before, or update_url=off, stays.
#
#   ./install.sh client [--hub URL]
#       On a Linux or macOS machine that requests builds. Puts `cider-build` in ~/.local/bin and saves
#       which hub it uses. Without cloning the repository, from the hub:
#         curl -fsSL https://<hub>:4710/bin/install.sh | bash -s client
#
#   install.sh worker [--slots N] [--user U] [--remove]
#       On a Mac that will build, as its user (or as root with --user). Downloaded from the hub:
#         curl -fsSL http://<hub IP or name>:4711/join | bash
#       Installs the tools and the agent, and registers the Mac with the hub. --remove takes it out of the fleet.
#
# An install from before the rename to Cider Builder (mac-build, ~/mac-build, com.mac-build.*) becomes this one
# the first time each command runs over it: the hub and the Macs keep their state, and a client keeps its hub.
#
# Optional variables:
#   CIDER_BUILD_HUB   hub URL for client and worker (the scripts the hub serves set it already); MAC_BUILD_HUB
#                     also works
#   PREFIX            folder for `cider-build` on the client (default ~/.local/bin)
set -euo pipefail

HUB_URL=${CIDER_BUILD_HUB:-${MAC_BUILD_HUB:-}}
# The PATH of both LaunchDaemon and LaunchAgent, and where install.sh looks for tailscale, so that what the check
# finds is what the daemons find: Homebrew's, or the Tailscale app's command-line tool in /usr/local/bin.
DAEMON_PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

say() { printf '%s\n' "$*" >&2; }
ok() { printf '  ✓ %s\n' "$*" >&2; }
warn() { printf '  ! %s\n' "$*" >&2; }
die() { printf 'Error: %s\n' "$1" >&2; exit "${2:-1}"; }

here=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fi

is_ssh_url() { # git URL: 0 if git reaches it over ssh (ssh://, or scp-like [user@]host:path)
  case $1 in
    ssh://*|git+ssh://*|ssh+git://*) return 0 ;;
    *://*|/*|./*|../*) return 1 ;;
  esac
  case ${1%%/*} in *:*) return 0 ;; esac
  return 1
}

redact() { # text: without the user:password@ of any scheme:// URL, as the hub's redact() does
  printf '%s\n' "$1" | sed -E 's#([A-Za-z][A-Za-z0-9+.-]*://)[^/@[:space:]]*@#\1#g'
}

clone_source() { # dir [command prefix]: "<remote URL>\n<branch>" of the clone whose top is dir; fails if it is not one
  local d=$1 top b remote="" merge="" url
  shift
  top=$("$@" git -C "$d" rev-parse --show-toplevel 2>/dev/null) && [ "$(cd "$top" && pwd -P)" = "$(cd "$d" && pwd -P)" ] ||
    return 1
  if b=$("$@" git -C "$d" symbolic-ref -q --short HEAD 2>/dev/null); then
    remote=$("$@" git -C "$d" config "branch.$b.remote" 2>/dev/null) || true
    merge=$("$@" git -C "$d" config "branch.$b.merge" 2>/dev/null) || true
  fi
  case $remote in ""|.) remote=origin merge="" ;; esac
  url=$("$@" git -C "$d" remote get-url "$remote" 2>/dev/null) && [ -n "$url" ] || return 1
  b=${merge#refs/heads/}
  if [ -z "$b" ]; then
    b=$("$@" git -C "$d" symbolic-ref -q --short "refs/remotes/$remote/HEAD" 2>/dev/null) && b=${b#"$remote"/} || b=main
  fi
  printf '%s\n%s\n' "$url" "$b"
}

migrate_hub() { # user home: the mac-build hub, from before the rename, becomes this one with its state
  local u=$1 home=$2 p f
  for p in /Library/LaunchDaemons/com.mac-build.hub.plist "$home/Library/LaunchAgents/com.mac-build.hub.plist"; do
    [ -e "$p" ] || continue
    launchctl bootout system/com.mac-build.hub 2>/dev/null || true
    launchctl bootout "gui/$(id -u "$u")/com.mac-build.hub" 2>/dev/null || true
    rm -f "$p"
    ok "stopped the mac-build hub and removed $p"
  done
  [ -d "$home/mac-build" ] && [ ! -e "$home/cider-build" ] || return 0
  mv "$home/mac-build" "$home/cider-build" || die "could not move $home/mac-build to $home/cider-build."
  # Its programs under their old names, and a rollback copy that a cider-build-hub could not run.
  for f in mac-build mac-build-hub mac-build-worker mac-build-panel.html .previous; do rm -rf "$home/cider-build/bin/$f"; done
  ok "moved $home/mac-build to $home/cider-build: jobs, Macs, cache and hub.json as they were"
}

install_hub() { # [--user U] [--set KEY=VALUE]...: as root (or with sudo); U is the user that runs the server
  [ "$(uname -s)" = Darwin ] || die "the hub must be a Mac."
  local u="" a sets=() orig=("$@") srcurl="" srcbranch="" s
  while [ $# -gt 0 ]; do
    a=$1; shift
    case $a in
      --user) u=${1:?--user needs a user}; shift ;;
      --set) case ${1:-} in ?*=*) sets+=("$1"); shift ;; *) die "--set needs KEY=VALUE, e.g. --set update_url=<git URL>" 2 ;; esac ;;
      --source) [ $# -ge 2 ] && [ -n "$1" ] && [ -n "$2" ] || die "--source needs a git URL and a branch." 2
                srcurl=$1 srcbranch=$2; shift 2 ;;
      *) die "unknown option: $a. Usage: install.sh hub [--user U] [--set KEY=VALUE]... [--source URL BRANCH]" 2 ;;
    esac
  done
  if [ "$(id -u)" -ne 0 ]; then
    [ -z "$u" ] || [ "$u" = "$(id -un)" ] || die "--user only works as root."
    say "  The server is installed as a system daemon (starts with the Mac, no login session needed): sudo is required."
    exec sudo bash "${BASH_SOURCE[0]}" hub --user "$(id -un)" ${orig[@]+"${orig[@]}"}  # macOS bash 3.2: empty arrays and set -u
  fi
  cd /tmp
  [ -n "$u" ] || u=${SUDO_USER:-}
  [ -n "$u" ] && [ "$u" != root ] || die "as root, say which user runs the server: install.sh hub --user <user>"
  id "$u" >/dev/null 2>&1 || die "user $u does not exist."
  local home src owner
  home=$(dscl . -read "/Users/$u" NFSHomeDirectory | awk '{print $2}')
  [ -d "$home" ] || die "cannot find the home folder of $u ($home)."
  if [ -n "$here" ] && [ -f "$here/bin/cider-build-hub" ]; then src=$here/bin       # a clone, or a copy of one
  elif [ -n "$here" ] && [ -f "$here/cider-build-hub" ]; then src=$here           # the hub's own ~/cider-build/bin
  else die "run it from a clone of the repository, or on the hub as: bash ~/cider-build/bin/install.sh hub"; fi
  /usr/bin/python3 -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null ||
    die "/usr/bin/python3 3.9 or later is missing. Install the Command Line Tools: xcode-select --install"
  local ts
  ts=$(PATH=$DAEMON_PATH; command -v tailscale) ||
    die "the hub runs with PATH=$DAEMON_PATH and finds no tailscale there. Install the Homebrew one (brew install tailscale) or the Tailscale app's command-line tool, and join it to the tailnet."
  "$ts" status >/dev/null 2>&1 || die "tailscale is not connected to the tailnet."
  ok "macOS, python3 and tailscale"

  owner=$(stat -f %Su "$here")
  if [ -z "$srcurl" ] && [ "$src" = "$here/bin" ] && s=$(clone_source "$here" sudo -u "$owner"); then
    srcurl=${s%%$'\n'*} srcbranch=${s#*$'\n'}
  fi

  migrate_hub "$u" "$home"
  local B=$home/cider-build f commit=""
  local plist=/Library/LaunchDaemons/com.cider-build.hub.plist
  sudo -u "$u" mkdir -p "$B/bin"
  if [ "$(cd "$src" && pwd -P)" = "$(cd "$B/bin" && pwd -P)" ]; then
    ok "programs in $B/bin, as they are (installing from there)"
  else
    rm -rf "$B/bin/.new"; sudo -u "$u" mkdir "$B/bin/.new"
    sudo -u "$u" cp -R "$src/." "$B/bin/.new/"
    [ -f "$src/install.sh" ] || sudo -u "$u" cp "$here/install.sh" "$B/bin/.new/install.sh"
    # One file at a time, so a Mac or a client downloading from the running hub never gets half a file.
    (cd "$B/bin/.new" && find . -type f) | while IFS= read -r f; do
      sudo -u "$u" mkdir -p "$(dirname "$B/bin/$f")"; mv "$B/bin/.new/$f" "$B/bin/$f"
    done
    rm -rf "$B/bin/.new"
    # The panel's Updates view compares bin/ with the update source; .commit names what is installed, only if it is
    # exactly a commit.
    if sudo -u "$owner" git -C "$here" rev-parse --git-dir >/dev/null 2>&1 && sudo -u "$owner" git -C "$here" diff --quiet HEAD 2>/dev/null; then
      commit=$(sudo -u "$owner" git -C "$here" rev-parse HEAD)
    fi
    if [ -n "$commit" ]; then printf '%s\n' "$commit" | sudo -u "$u" tee "$B/bin/.commit" >/dev/null; else rm -f "$B/bin/.commit"; fi
    ok "programs in $B/bin (clients and builder Macs download them from here)${commit:+; commit ${commit:0:12}}"
  fi

  # The hub's own parser is the only judge of its settings: a bad --set changes nothing, and nothing restarts on a
  # hub.json the new programs cannot read.
  hubcfg() { sudo -u "$u" -H env CIDER_BUILD_HOME="$B" /usr/bin/python3 "$B/bin/cider-build-hub" config "$@"; }
  # The source this copy came from, only on a hub that never chose one and when --set does not choose now.
  for a in ${sets[@]+"${sets[@]}"}; do case $a in update_url=*) srcurl="" ;; esac; done
  if [ -n "$srcurl" ] && s=$(hubcfg get update_url 2>/dev/null) && [ -z "$s" ]; then
    sets=("update_url=$srcurl" "update_branch=$srcbranch" ${sets[@]+"${sets[@]}"})
  fi
  if [ -n "${sets+x}" ]; then
    s=$(hubcfg set "${sets[@]}" 2>&1 >/dev/null) || { say "$(redact "$s")"; die "$B/hub.json is as it was (reason above)." 2; }
  fi
  hubcfg >/dev/null || die "the hub cannot start with $B/hub.json (reason above). Change it with --set KEY=VALUE."
  local port tport url key
  port=$(hubcfg get port) tport=$(hubcfg get tailnet_port) url=$(hubcfg get update_url) key=$(hubcfg get update_ssh_key)
  if [ "$url" = off ]; then url=""; fi
  # A deploy key only for an ssh update source, and the one already there if there is one.
  if [ -n "$url" ] && [ -z "$key" ] && is_ssh_url "$url"; then
    key=$home/.ssh/cider-build-deploy
    # The key a mac-build hub made before the rename, already accepted by the git host.
    [ -f "$key" ] || [ ! -f "$home/.ssh/mac-build-deploy" ] || key=$home/.ssh/mac-build-deploy
    sudo -u "$u" mkdir -p "$home/.ssh"; chmod 700 "$home/.ssh"
    [ -f "$key" ] || sudo -u "$u" ssh-keygen -q -t ed25519 -N "" -C "cider-build hub $(hostname -s)" -f "$key" ||
      die "could not create the deploy key $key."
    hubcfg set "update_ssh_key=$key" >/dev/null
  fi
  ok "settings in $B/hub.json (list them: $B/bin/cider-build-hub config)"

  cat > "$plist.new" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cider-build.hub</string>
  <key>UserName</key><string>$u</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/python3</string><string>$B/bin/cider-build-hub</string></array>
  <key>WorkingDirectory</key><string>$B</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$DAEMON_PATH</string>
    <key>HOME</key><string>$home</string>
    <key>USER</key><string>$u</string>
    <key>CIDER_BUILD_HOME</key><string>$B</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$B/hub.log</string>
  <key>StandardErrorPath</key><string>$B/hub.log</string>
</dict>
</plist>
PLIST
  chown root:wheel "$plist.new"; chmod 644 "$plist.new"; mv "$plist.new" "$plist"
  launchctl bootout system/com.cider-build.hub 2>/dev/null || true
  local n=0
  until launchctl bootstrap system "$plist" 2>/dev/null; do
    n=$((n + 1)); [ "$n" -lt 10 ] || die "launchctl could not load $plist."
    sleep 1
  done
  n=0
  until /usr/bin/curl -fsS -o /dev/null "http://127.0.0.1:$port/status" 2>/dev/null; do
    n=$((n + 1))
    if [ "$n" -ge 15 ]; then tail -20 "$B/hub.log" >&2; die "the server is not responding on 127.0.0.1:$port (log above)."; fi
    sleep 1
  done
  ok "server running as $u (LaunchDaemon com.cider-build.hub: starts with the Mac; log in $B/hub.log)"

  if ! "$ts" serve status --json 2>/dev/null | grep -q "\"$port\""; then
    "$ts" serve --bg --https="$port" "http://127.0.0.1:$port" >/dev/null ||
      die "could not publish port $port on the tailnet (tailscale serve needs HTTPS certificates enabled for the tailnet)."
  fi
  local dns
  dns=$("$ts" status --json | /usr/bin/python3 -c 'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
  ok "published at https://$dns:$port (tailnet only); the panel is at https://$dns:$port/"
  local ip
  ip=$("$ts" ip -4 | head -1)
  n=0
  until /usr/bin/curl -fsS -o /dev/null "http://$ip:$tport/status" 2>/dev/null; do
    n=$((n + 1))
    if [ "$n" -ge 15 ]; then tail -20 "$B/hub.log" >&2; die "the server is not responding on http://$ip:$tport (log above)."; fi
    sleep 1
  done
  ok "also on http://$ip:$tport (tailnet IP only, for joining new Macs)"
  say ""
  say "Hub ready. On each machine that requests builds:"
  say "  curl -fsSL https://$dns:$port/bin/install.sh | bash -s client"
  say "On each Mac that builds, on that Mac and as its user, any of these:"
  say "  curl -fsSL https://$dns:$port/join | bash"
  say "  curl -fsSL http://$ip:$tport/join | bash"
  say "  curl -fsSL http://${dns%%.*}:$tport/join | bash"
  say "Or from a client, over Tailscale SSH as root: cider-build add <mac>"
  say ""
  if [ -z "$url" ]; then
    say "Hub updates: off. To update this hub from a git repository (this project's, or your fork):"
    say "  bash $B/bin/install.sh hub --set update_url=<git URL> [--set update_branch=<branch>]"
  else
    say "Hub updates: from $(redact "$url"), branch $(hubcfg get update_branch), in the panel's Fleet > Updates."
    say "To turn them off: bash $B/bin/install.sh hub --set update_url=off"
    if [ -n "$key" ] && [ -f "$key.pub" ]; then
      say "The hub reads that repository with the SSH key $key. Give this public key read-only"
      say "access to it on its git host (usually called a deploy key):"
      say "  $(cat "$key.pub")"
    fi
  fi
}

install_client() { # [--hub URL]: the hub defaults to the one that served this script
  local prefix=${PREFIX:-$HOME/.local/bin} hub=$HUB_URL c missing=""
  while [ $# -gt 0 ]; do
    case $1 in
      --hub) [ $# -ge 2 ] || die "missing URL after --hub." 2; hub=${2%/}; shift 2 ;;
      *) die "unknown option: $1. Usage: install.sh client [--hub URL]" 2 ;;
    esac
  done
  for c in bash curl python3 tar git; do command -v "$c" >/dev/null || missing="$missing $c"; done
  [ -z "$missing" ] || die "missing programs:$missing"
  ok "bash, curl, python3, tar and git"
  command -v ssh >/dev/null && command -v scp >/dev/null && ok "ssh and scp (for cider-build add, remove and hub-install)" ||
    warn "no ssh or scp: building works, but you will not be able to use cider-build add, remove or hub-install"
  if command -v node >/dev/null || ls -d "$HOME"/.local/share/mise/installs/node/*/bin/node >/dev/null 2>&1; then
    ok "node (for the cache key of Expo and React Native projects)"
  else
    warn "no node: Expo and React Native projects need node and their node_modules to compute the cache key"
  fi

  mkdir -p "$prefix"
  if [ -n "$here" ] && [ -f "$here/bin/cider-build" ]; then
    cp "$here/bin/cider-build" "$prefix/.cider-build.new"
    ok "cider-build from the repository ($here)"
  else
    [ -n "$hub" ] || die "which hub? Install from it: curl -fsSL https://<hub>:4710/bin/install.sh | bash -s client" 2
    curl -fsS --connect-timeout 10 -o "$prefix/.cider-build.new" "$hub/bin/cider-build" ||
      die "could not download cider-build from $hub. Is this machine on the tailnet?"
    ok "cider-build from the hub ($hub)"
  fi
  bash -n "$prefix/.cider-build.new" || die "the downloaded cider-build is not a valid script."
  chmod 755 "$prefix/.cider-build.new"
  mv "$prefix/.cider-build.new" "$prefix/cider-build"
  ok "installed at $prefix/cider-build"
  # mac-build is this client's name from before the rename: scripts and git hooks that call it keep working.
  if [ -f "$prefix/mac-build" ] && [ ! -L "$prefix/mac-build" ]; then
    ln -sfn cider-build "$prefix/mac-build"
    ok "$prefix/mac-build now runs cider-build (the old name, for scripts and hooks that still use it)"
  fi
  case ":$PATH:" in
    *":$prefix:"*) ;;
    *) warn "$prefix is not in your PATH. Add to your shell: export PATH=\"$prefix:\$PATH\"" ;;
  esac

  # cider-build owns where its hub is saved; the CIDER_BUILD_HUB this script may carry must not mask the saved one.
  if [ -n "$hub" ]; then
    CIDER_BUILD_HUB="" "$prefix/cider-build" hub "$hub" || die "could not save the hub for cider-build."
  elif ! CIDER_BUILD_HUB="" "$prefix/cider-build" hub >/dev/null 2>&1; then
    warn "cider-build does not know its hub yet. Tell it which one: cider-build hub https://<hub>:4710"
    return
  fi
  say ""
  if CIDER_BUILD_HUB="" "$prefix/cider-build" status | sed -n '1,/^$/p'; then
    say "Done. In an app folder: cider-build ios  (or android). Help: cider-build --help"
    say "For coding agents (Claude Code, Cursor, Codex and others): npx skills add dtowers10/cider-builder --skill cider-build -g"
  else
    warn "the hub is not responding; cider-build is installed, but it cannot build until it reaches the hub"
  fi
}

# --- builder Mac ----------------------------------------------------------------------------------
# Runs on the Mac itself: as the user that builds (the usual case) or as root from `cider-build add`.
# sudo only for what needs it and only if missing; a Mac that is already set up is asked for nothing.
# stdin is /dev/null (see the case at the end); sudo asks for the password on the terminal, not on stdin.

as() { # user command…: as that user, with sudo only if it is not the current one
  local who=$1; shift
  if [ "$who" = "$(id -un)" ]; then "$@"
  else sudo -u "$who" -H env PATH="$PATH" HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 JAVA_HOME="$JAVA_HOME" "$@"; fi
}

admin() { # command…: as root; if we are not root, sudo asks for the password on the terminal
  if [ "$(id -u)" -eq 0 ]; then "$@" || die "failed: $*"; return; fi
  say "  Your administrator password is needed for: $*"
  sudo "$@" || die "could not run with sudo: $*. Repeat from the Mac's Terminal, as an administrator user."
}

place() { # user file: writes stdin to the file if its content changes; exits 0 if it changed
  as "$1" tee "$2.new" >/dev/null || die "could not write $2.new"
  if cmp -s "$2.new" "$2"; then as "$1" rm -f "$2.new"; return 1; fi
  as "$1" mv "$2.new" "$2" || die "could not write $2"
}

admit() { # label host: the hub decides whether this Mac may build, before anything on it changes
  local r
  r=$(curl -s --fail-with-body "$HUB_URL/workers/$1/admit?host=$2") || die "${r:-cannot talk to the hub ($HUB_URL).}" 2
}

tailnet_label() { # HostName of this Mac on the tailnet; empty if tailscale is not connected
  local ts
  ts=$(command -v tailscale || true)
  [ -n "$ts" ] || ts=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  "$ts" status --json 2>/dev/null | /usr/bin/python3 -c '
import json, sys
st = json.load(sys.stdin)
print(st["Self"]["HostName"] if st.get("BackendState") == "Running" else "")' 2>/dev/null || true
}

worker_state() { # label: its state code in the hub's /api/state (online, drained, no_tools, ...), empty if unknown
  curl -fsS "$HUB_URL/api/state" 2>/dev/null | /usr/bin/python3 -c '
import json, sys
print(next((w["state"] for w in json.load(sys.stdin)["workers"] if w["label"] == sys.argv[1]), ""))' "$1" 2>/dev/null || true
}

build_user() { # who builds when running as root: whoever already has the agent, otherwise whoever is logged in
  local p
  for p in /Users/*/Library/LaunchAgents/com.{cider,mac}-build.worker.plist; do
    if [ -e "$p" ]; then stat -f %Su "$p"; return; fi
  done
  stat -f %Su /dev/console
}

provision() { # user home: Xcode, Homebrew, JDK, Android SDK; installs only what is missing
  local u=$1 home=$2 bu f p sdk need="" t
  xcodebuild -version >/dev/null 2>&1 || die "Xcode is missing. Install it on this Mac (App Store or xcodes; needs an Apple ID) with the same version as the rest of the fleet, the one in the XCODE column of: curl -fsS $HUB_URL/status. Then repeat."
  ok "$(xcodebuild -version | head -1)"
  xcodebuild -license check >/dev/null 2>&1 || { admin xcodebuild -license accept; ok "Xcode license accepted"; }
  xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1 || { admin xcodebuild -runFirstLaunch >/dev/null; ok "Xcode components installed"; }
  if ! xcrun simctl list runtimes 2>/dev/null | grep -q '^iOS'; then
    say "  Downloading the iOS simulator (several GB, takes a while)…"; as "$u" xcodebuild -downloadPlatform iOS >/dev/null
  fi

  if [ ! -x /opt/homebrew/bin/brew ]; then
    [ "$(id -u)" -ne 0 ] || die "Homebrew is missing. On the Mac, as an administrator user: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\" and repeat."
    say "  Installing Homebrew…"
    sudo -v || die "Homebrew needs an administrator user. Repeat from the Mac's Terminal."
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" ||
      die "could not install Homebrew."
  fi
  bu=$(stat -f %Su /opt/homebrew)
  for f in node@22 cocoapods xcodegen openjdk@17; do
    [ -d "/opt/homebrew/opt/$f" ] || { say "  Installing ${f}…"; as "$bu" brew install -q "$f" >/dev/null; }
  done
  [ -x /opt/homebrew/bin/node ] || as "$bu" brew link --overwrite --force node@22 >/dev/null
  [ -e /Library/Java/JavaVirtualMachines/openjdk-17.jdk ] ||
    admin ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk
  [ -d /opt/homebrew/Caskroom/android-commandlinetools ] ||
    { say "  Installing Android command-line tools…"; as "$bu" brew install -q --cask android-commandlinetools >/dev/null; }
  sdk=$home/Library/Android/sdk
  as "$u" mkdir -p "$sdk" "$home/builds"
  for p in platform-tools "platforms;android-36" "build-tools;36.0.0"; do [ -d "$sdk/${p//;//}" ] || need="$need $p"; done
  yes | as "$u" sdkmanager --sdk_root="$sdk" --licenses >/dev/null 2>&1 || true
  if [ -n "$need" ]; then say "  Installing Android SDK:${need}…"; as "$u" sdkmanager --sdk_root="$sdk" $need >/dev/null 2>&1; fi

  for t in "node -v" "pod --version" "xcodegen --version" "$JAVA_HOME/bin/java -version" "$sdk/platform-tools/adb version"; do
    as "$u" $t >/dev/null 2>&1 || die "check failed on this Mac: $t"
  done
  ok "tools ready: Xcode, node, CocoaPods, xcodegen, JDK 17, Android SDK"
}

install_agent() { # user home label: downloads the agent from the hub and (re)starts it only if something changed or it is not running
  local u=$1 home=$2 label=$3 uid d plist tmp f changed="" n state
  uid=$(id -u "$u") d=$home/cider-build plist=$home/Library/LaunchAgents/com.cider-build.worker.plist
  # The mac-build agent, from before the rename: it stops (its builds go back to the queue) and its folder moves.
  if [ -e "$home/Library/LaunchAgents/com.mac-build.worker.plist" ]; then
    launchctl bootout "gui/$uid/com.mac-build.worker" 2>/dev/null || true
    rm -f "$home/Library/LaunchAgents/com.mac-build.worker.plist"
    ok "stopped the mac-build agent"
  fi
  if [ -d "$home/mac-build" ] && [ ! -e "$d" ]; then
    mv "$home/mac-build" "$d" || die "could not move $home/mac-build to $d."
    rm -f "$d/mac-build-worker"
    ok "moved $home/mac-build to $d"
  fi
  as "$u" mkdir -p "$d" "$home/Library/LaunchAgents"
  tmp=$(mktemp)
  for f in cider-build-worker build.sh; do
    /usr/bin/curl -fsS --retry 3 -o "$tmp" "$HUB_URL/bin/$f" || die "could not download $f from $HUB_URL."
    if place "$u" "$d/$f" <"$tmp"; then changed=1; fi
    as "$u" chmod 755 "$d/$f"
  done
  rm -f "$tmp"
  if printf '{"label": "%s", "hub": "%s"}\n' "$label" "$HUB_URL" | place "$u" "$d/worker.json"; then changed=1; fi
  if place "$u" "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cider-build.worker</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/python3</string><string>$d/cider-build-worker</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$DAEMON_PATH</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardOutPath</key><string>$d/worker.log</string>
  <key>StandardErrorPath</key><string>$d/worker.log</string>
</dict>
</plist>
PLIST
  then changed=1; fi

  state=$(launchctl print "gui/$uid/com.cider-build.worker" 2>/dev/null || true)
  case $state in *"state = running"*) [ -n "$changed" ] || { ok "agent up to date and running; not restarting it"; return; } ;; esac
  # Restarting the agent sends whatever it is building back to the queue; so only if something changed or it is not running.
  launchctl bootout "gui/$uid/com.cider-build.worker" 2>/dev/null || true
  n=0
  until launchctl bootstrap "gui/$uid" "$plist" 2>/dev/null; do
    n=$((n + 1)); [ "$n" -lt 10 ] || die "launchctl could not load the agent for $u. Is $u logged in to a graphical session on this Mac?"
    sleep 1
  done
  sleep 2
  state=$(launchctl print "gui/$uid/com.cider-build.worker" 2>/dev/null || true)
  case $state in *"state = running"*) ;; *) tail -20 "$d/worker.log" >&2; die "the agent did not start (log above, in $d/worker.log)." ;; esac
  ok "agent running as $u (log in $d/worker.log)"
}

remove_worker() { # label: the hub stops sending it jobs, waits for its own to finish and removes the agent
  local label=$1 r plist u name
  r=$(curl -fsS -X DELETE "$HUB_URL/workers/$label") || die "cannot talk to the hub ($HUB_URL)."
  while [ "${r#running }" != 0 ]; do
    say "  $label no longer receives new builds. Waiting for its ${r#running } running build(s) to finish…"
    sleep 10; r=$(curl -fsS "$HUB_URL/workers/$label") || die "cannot talk to the hub ($HUB_URL)."
  done
  # com.mac-build.worker is the agent from before the rename, in ~/mac-build/mac-build-worker.
  for plist in /Users/*/Library/LaunchAgents/com.{cider,mac}-build.worker.plist; do
    [ -e "$plist" ] || continue
    u=$(stat -f %Su "$plist") name=${plist##*/com.} name=${name%.worker.plist}
    [ "$(id -u)" -eq 0 ] || [ "$u" = "$(id -un)" ] || continue
    launchctl bootout "gui/$(id -u "$u")/com.$name.worker" 2>/dev/null || true
    rm -f "$plist"
    as "$u" /usr/bin/python3 "${plist%/Library/LaunchAgents/*}/$name/$name-worker" reap 2>/dev/null || true
    ok "agent for $u removed"
  done
  ok "$label removed from the build fleet"
}

install_worker() {
  local slots="" want="" remove="" host label me u home gb n st
  while [ $# -gt 0 ]; do
    case $1 in
      --slots) [ $# -ge 2 ] || die "missing number after --slots." 2; slots=$2; shift 2 ;;
      --user) [ $# -ge 2 ] || die "missing user after --user." 2; want=$2; shift 2 ;;
      --remove) remove=1; shift ;;
      *) die "unknown option: $1. Usage: install.sh worker [--slots N] [--user U] [--remove]" 2 ;;
    esac
  done
  case $slots in ""|[1-9]|[1-9][0-9]) ;; *) die "--slots must be a number between 1 and 99." 2 ;; esac

  [ -n "$HUB_URL" ] || die "which hub? Run this through the hub: curl -fsSL http://<hub>:4711/join | bash" 2
  [ "$(uname -s)" = Darwin ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] ||
    die "only Apple Silicon Macs can build." 2
  host=$(scutil --get LocalHostName 2>/dev/null || true)
  export PATH=$DAEMON_PATH HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
  export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
  label=$(tailnet_label)
  [ -n "$label" ] || die "this Mac is not connected to the tailnet. Install Tailscale (brew install tailscale, or the app),
connect it to the hub's tailnet (sudo tailscale up; add --ssh so that cider-build add can reach it from a client)
and repeat this command."
  cd /tmp

  if [ -n "$remove" ]; then remove_worker "$label"; return; fi
  admit "$label" "$host"

  me=$(id -un)
  if [ "$me" = root ]; then
    u=${want:-$(build_user)}
    [ -n "$u" ] && [ "$u" != root ] || die "cannot tell which user should build: nobody is logged in and no user has the agent. Use --user <user>."
  else
    [ -z "$want" ] || [ "$want" = "$me" ] || die "--user only works as root. With your own user, this Mac builds as $me." 2
    u=$me
  fi
  home=$(dscl . -read "/Users/$u" NFSHomeDirectory 2>/dev/null | awk '{print $2}')
  [ -n "$home" ] || die "user $u does not exist on this Mac."
  gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  [ -n "$slots" ] || slots=$(( gb / 24 > 0 ? gb / 24 : 1 ))
  say "Adding $label to the fleet at $HUB_URL (user $u, $gb GB of RAM, $slots slot(s))."

  provision "$u" "$home"
  install_agent "$u" "$home" "$label"
  curl -fsS -o /dev/null -X PUT "$HUB_URL/workers/$label?slots=$slots&user=$u&ram=$gb" ||
    die "cannot register $label with the hub ($HUB_URL)."
  ok "registered with the hub with $slots slot(s)"

  n=0
  until st=$(worker_state "$label") && { [ "$st" = online ] || [ "$st" = drained ]; }; do
    n=$((n + 1))
    [ "$n" -lt 20 ] || die "$label is not online after 40 s (state: ${st:-unknown}). See $home/cider-build/worker.log."
    sleep 2
  done
  say ""
  curl -fsS "$HUB_URL/status" 2>/dev/null | grep -E "^(MAC|${label}) " >&2 || true
  [ "$st" != drained ] || warn "the hub's drain_command keeps this Mac out of the pool: no builds until it stops listing it."
  say ""
  say "Done: $label builds for the fleet."
}

case "${1:-}" in
  hub) shift; install_hub "$@" ;;
  source) clone_source "${2:-.}" ;;  # for cider-build hub-install
  client) shift; install_client "$@" ;;
  worker) shift; install_worker "$@" </dev/null ;;
  *) sed -n '2,/^set -e/{/^#/p;}' "${BASH_SOURCE[0]:-$0}" 2>/dev/null | sed 's/^# \{0,1\}//' >&2 || true
     say "Usage: install.sh hub [--user U] [--set KEY=VALUE]... [--source URL BRANCH] | install.sh client [--hub URL] | install.sh worker [--slots N] [--user U] [--remove]"
     exit 2 ;;
esac
