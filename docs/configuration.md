# Configuration

The hub reads its settings from `~/cider-build/hub.json` (`$CIDER_BUILD_HOME/hub.json`) when it starts. Reinstalls and hub updates leave that file alone. Every setting has a default, so a hub runs with no file at all.

Change settings with `install.sh hub --set KEY=VALUE` (repeatable; an empty VALUE puts back the default), which restarts the hub. On the hub, `~/cider-build/bin/cider-build-hub config` lists every setting with its value and where the value comes from, and `cider-build-hub config set KEY=VALUE` writes the file without restarting. You can also edit the JSON by hand and restart the hub with `sudo launchctl kickstart -k system/com.cider-build.hub`. A value the hub cannot use stops it with one line in `~/cider-build/hub.log`, and `cider-build-hub config` prints the same line. An unknown key is only a warning.

| Setting | Default | Meaning |
|---|---|---|
| `port` | 4710 | Port on 127.0.0.1. `tailscale serve` publishes the same port as `https://<hub>:<port>`, the URL clients use. |
| `tailnet_port` | 4711 | Plain-HTTP port on the hub's tailnet IP, for `/join` on a new Mac. |
| `update_url` | the repository `install.sh hub` ran from | Git repository the hub updates itself from: ssh, https or a local path. `off`: hub updates off, and reinstalls keep it off. Unset (installed from a copy with no git): off until an install from a clone fills it in. |
| `update_branch` | the branch `install.sh hub` ran from, else `main` | Branch of `update_url`. |
| `update_ssh_key` | none: ssh's defaults | Private key for an ssh `update_url`. `install.sh hub` sets it when it creates `~/.ssh/cider-build-deploy`. |
| `update_check_s` | 1800 | Seconds between automatic update checks. 0 checks only when you click "Check for updates". |
| `exclude` | none | Macs that never build, by tailnet name, as a JSON list or comma-separated. The hub never builds, listed or not. |
| `drain_command` | none | Shell command the hub runs every 10 s. The Macs it prints, one per line, stay out of the pool: they get no builds and show `out of the pool`. If the command fails, the last list stays. |
| `cache_keep` | 5 | Artifacts kept per project and platform in the hub cache. |
| `cache_prune_s` | 600 | Seconds between cache prunes. |

For example:

```json
{
  "update_url": "git@git.example.com:you/cider-builder.git",
  "update_ssh_key": "/Users/builds/.ssh/cider-build-deploy",
  "exclude": ["my-laptop"],
  "drain_command": "/Users/builds/bin/macs-out-of-pool"
}
```

Each setting can also come from an environment variable, which wins over the file: `CIDER_BUILD_PORT`, `CIDER_BUILD_TAILNET_PORT`, `CIDER_BUILD_REPO` (`update_url`), `CIDER_BUILD_BRANCH`, `CIDER_BUILD_UPDATE_SSH_KEY`, `CIDER_BUILD_UPDATE_CHECK_S`, `CIDER_BUILD_EXCLUDE`, `CIDER_BUILD_DRAIN_COMMAND`, `CIDER_BUILD_CACHE_KEEP` and `CIDER_BUILD_CACHE_PRUNE_S`. The LaunchDaemon sets none of them, so on a hub the file decides. The tests and the hub's test start of a new release use them.

The client keeps one setting, its hub's URL, in `${XDG_CONFIG_HOME:-~/.config}/cider-build/hub`. `cider-build hub <URL>` writes it, and `CIDER_BUILD_HUB` overrides it.
