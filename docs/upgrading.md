# Upgrading

## Upgrading from mac-build

Cider Builder was called mac-build. Its commands were `mac-build`, `mac-build-hub` and `mac-build-worker`, its state was in `~/mac-build`, its launchd jobs were `com.mac-build.hub` and `com.mac-build.worker`, and its variables were `MAC_BUILD_*`. A mac-build hub cannot update itself from the panel to this version, because the files it updates are no longer in the repository. Upgrade in this order:

1. The hub, once, from a client with a clone of this version, as with any `hub-install`. A hub installed before `hub.json` follows [Upgrading a hub installed before hub.json](#upgrading-a-hub-installed-before-hubjson) instead.

   ```bash
   bin/cider-build hub-install <hub user>@<hub>
   ```

   `install.sh hub` stops `com.mac-build.hub` and removes its plist, moves `~/mac-build` to `~/cider-build` with its jobs, Macs, cache and `hub.json`, and starts `com.cider-build.hub` on the same ports. The tailnet URL does not change. An ssh update source keeps using `~/.ssh/mac-build-deploy`, because `hub.json` names it.
2. Each client, from the hub. It installs `cider-build` next to `mac-build`, keeps the saved hub and turns `mac-build` into a link to `cider-build`, so hooks and scripts that call `mac-build` keep working.

   ```bash
   curl -fsSL https://<hub>:4710/bin/install.sh | bash -s client
   ```

3. Each builder Mac, from a client, or on the Mac with `curl -fsSL http://<hub>:4711/join | bash`. It stops `com.mac-build.worker`, which sends its builds back to the queue, moves `~/mac-build` to `~/cider-build` and starts `com.cider-build.worker`.

   ```bash
   cider-build add <mac>
   ```

   Until then the Mac keeps building with its old agent. "Update agent" in the panel also works on it, and the updated agent keeps running from `~/mac-build`.

What stays as it was:

- `MAC_BUILD_*` variables, when the `CIDER_BUILD_*` one of the same name is not set.
- A project's `.mac-build.json`, when it has no `.cider-build.json`. The cache key does not change.
- The client's saved hub in `~/.config/mac-build/hub`, until `cider-build hub <URL>` saves one in `~/.config/cider-build/hub`.

The client's local cache moves to `~/.cache/cider-build`, so each project downloads its artifacts from the hub once. You can delete `~/.cache/mac-build`.

## Upgrading a hub installed before hub.json

Earlier versions had the hub's settings in the code. These steps also do the rename from mac-build in [Upgrading from mac-build](#upgrading-from-mac-build). The update source, the Macs that never build and the out-of-pool list now come from `hub.json`. Do this once, from a client with a clone of this version. Use `hub-install` rather than the panel's "Update hub". An older hub test-starts the new one without its settings, so after a panel update the hub would run with none until you set them.

1. If the hub took Macs out of the pool from another tool, put a script on the hub that prints those Macs, one per line, and make it executable.
2. In your clone, check out the branch the hub should follow (usually `main`). Its remote (`git remote get-url origin`, or the remote that branch tracks) should be the repository the hub updated from. `hub-install` gives the hub that remote and branch, because the hub has no `hub.json` yet.
3. Reinstall the hub with its settings. An ssh remote picks up the existing `~/.ssh/mac-build-deploy`, so the key on the git host stays valid.

   ```bash
   bin/cider-build hub-install <hub user>@<hub> \
     --set exclude=<Macs that must not build, comma-separated> \
     --set drain_command=<absolute path of the script from step 1>
   ```

   Write the script's full path, because your shell would expand a `~` on the client. The summary says `Hub updates: from <remote>, branch <branch>`. To follow another repository, add `--set update_url=<git URL>`, and to keep updates off, `--set update_url=off`.
4. On each client, install from the hub once, so it saves the hub and needs no `MAC_BUILD_HUB`:

   ```bash
   curl -fsSL https://<hub>:4710/bin/install.sh | bash -s client
   ```

Builder Macs keep building, because their `~/mac-build/worker.json` already names the hub. Update their agents from the panel as usual, and move them to `~/cider-build` with `cider-build add <mac>` as in [Upgrading from mac-build](#upgrading-from-mac-build). The hub's own name no longer needs to be in `exclude`, because the hub refuses itself.
