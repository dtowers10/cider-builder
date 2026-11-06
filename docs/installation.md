# Installation

Everything is installed with `install.sh`, which can be repeated to update. Anything already in place is left as is. The examples use `buildhub` as the hub's tailnet name and `example.ts.net` as the tailnet's domain. Use yours.

**Network requirements.**
- The hub, the builder Macs and the clients are on the same tailnet, with MagicDNS and HTTPS certificates on (`tailscale serve` needs them).
- The Macs can talk to each other over the tailnet.
- For `cider-build add` and `remove` from a client, the client needs Tailscale SSH as `root@` on each builder Mac, which your tailnet policy must allow. Joining a Mac from the Mac itself does not need it.

**1. The hub.** On the Mac that acts as the hub, as the user that will run the server (it asks for the administrator password), or as root with `--user <user>`:

```bash
git clone <this repository's URL> cider-builder && cd cider-builder
./install.sh hub
```

It does this:
- Checks that macOS, `/usr/bin/python3` and tailscale are present. Tailscale must be on the daemon's PATH: Homebrew's (`/opt/homebrew/bin`), or the Tailscale app's command-line tool (`/usr/local/bin`).
- Copies `bin/` and `install.sh` to `~/cider-build/bin`.
- Applies any `--set KEY=VALUE` to `~/cider-build/hub.json` (see [Configuration](configuration.md)), after checking every value with the new hub. A bad value stops the install and changes nothing.
- If the hub has no `update_url` yet and you did not pass one, records the update source: the clone's remote (the one its current branch tracks, else `origin`) and that branch (else the remote's default branch, else `main`). From a copy that is not a git clone, nothing, and hub updates stay off. An ssh remote gets a deploy key (see [Updates](updates.md)).
- Installs the LaunchDaemon `com.cider-build.hub` (`/Library/LaunchDaemons`), which runs as that user, and waits for the server to respond. It starts with the Mac even if nobody logs in, and launchd restarts it if it crashes. If there was a LaunchAgent from an earlier version, it removes it.
- Publishes the hub's port (4710) on the tailnet with `tailscale serve`.
- Checks that the server also responds on `http://<tailnet IP>:4711`. That port listens only on the tailnet IP, not on the local network. It has no TLS because the tailnet already encrypts and authenticates, and because `tailscale serve` only answers on the full name.
- Ends with the commands for clients and builder Macs, and whether hub updates are on, with the source and the command that turns them off or on. A user and password in a URL are never printed.

To change a setting later, run it again with `--set`, from the clone or from the hub's own copy: `bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>`. Settings you do not pass keep their value. `--set update_url=off` turns hub updates off for good, and `--set update_url=` forgets the source so that the next install from a clone records it again.

From a client with this repository, `bin/cider-build hub-install` does the same over Tailscale SSH, without cloning anything on the hub. It uploads `install.sh` and `bin/` as the hub user, then runs `install.sh hub` as `root@` with the options you pass, plus `--source <remote> <branch>` from the client's clone. `install.sh` takes that source only for a hub with no `update_url` yet, as it would from a clone of its own. The first time, name the target: `bin/cider-build hub-install <hub user>@buildhub.example.ts.net`. After that, it finds the hub and its user from the client's hub.

**2. Each client** (Linux or macOS). Install it from the hub, without the repository:

```bash
curl -fsSL https://buildhub.example.ts.net:4710/bin/install.sh | bash -s client
```

The script the hub serves names that hub, so the client saves it in `~/.config/cider-build/hub` and `cider-build` needs no variable in your shell. It checks the dependencies (bash, curl, python3, tar and git; node for Expo and React Native), puts `cider-build` in `~/.local/bin` (change the folder with `PREFIX`) and shows the hub's status. From a clone, run `./install.sh client --hub https://buildhub.example.ts.net:4710`. `cider-build hub` prints the hub in use, and `cider-build hub <URL>` changes it. `CIDER_BUILD_HUB=<URL>` overrides it for one command.

**3. Each Mac that builds.** With Xcode already installed and the Mac on the tailnet, open Terminal on that Mac as the user that will build and paste one of these (the hub's full name, IP or short name all work):

```bash
curl -fsSL http://buildhub:4711/join | bash
curl -fsSL http://buildhub:4711/join | bash -s -- --slots 2   # slots; default 1 per 24 GB of RAM
```

It does this, in this order:
- Refuses to continue if the Mac is not Apple Silicon.
- Checks that Tailscale is connected. The Mac's name in the fleet is its tailnet name.
- Asks the hub whether this Mac may build, before touching anything. The hub refuses itself and the Macs in its `exclude` setting.
- Installs whatever is missing: Homebrew, node, CocoaPods, xcodegen, JDK 17 and the Android SDK. It asks for the administrator password only for what needs it (Xcode license, the JDK link in `/Library`, installing Homebrew), and only if missing. On a Mac that is already set up it asks for nothing.
- Installs or updates the agent (`~/cider-build`, LaunchAgent `com.cider-build.worker`). It only restarts it if something changed, so repeating it does not interrupt builds.
- Registers it with the hub with its RAM and slots, and waits until it shows `online` in `cider-build status`.

If Xcode is missing, it stops and explains how to install it, because that needs an Apple ID.

From a client, over Tailscale SSH as `root@`, `cider-build add` does the same without sitting in front of the Mac. It reaches `root@<mac>.<the hub's tailnet domain>`, or the name as you typed it if it has a dot. The user that builds is the one that already has the agent or, if none does, whoever is logged in. `--user` picks another. As root it does not install Homebrew: if it is missing, it stops and explains how to install it.

```bash
cider-build add mac-mini-2
cider-build add mac-studio 3 --user ci   # 3 slots, builds as the macOS user ci
```

`cider-build remove <mac>` stops sending it jobs, waits for its own to finish and removes its agent. On the Mac itself, `curl -fsSL http://buildhub:4711/join | bash -s -- --remove` does the same.
