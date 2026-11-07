# The panel and updates

## Panel

The hub serves a web panel at `https://<hub>:4710/` and at `http://<hub's tailnet IP>:4711/`. It opens from any browser on the tailnet.

It shows the Macs with their state, slots, RAM, Xcode and last heartbeat. It also shows the builds in progress, the queue, the history with filters, the cache with its downloads, affinity and the commands to join a Mac. Each job has its live log.

From the panel you can cancel a job, change a Mac's slots, disable or enable it, and update the hub and the agents (see [Updates](updates.md)). In the cache view you can invalidate one artifact or delete a project's whole cache, so the next cider-build for it rebuilds on a Mac. Every action that changes something asks for confirmation before calling the hub.

The panel only reads the hub through `/api/state`, `/api/history`, `/api/cache`, `/api/job` and `/poll`, all JSON except `/poll`. Cancelling uses `POST /detach?job=<id>&all=1`, which cancels the job for every client waiting on it. Updates use `POST /hub/check`, `POST /hub/update` and `POST /workers/<mac>/update`. Invalidating uses `DELETE /cache/<project>/<file>` and deleting a project's cache `DELETE /cache/<project>`.

## Updates

The panel's Fleet > Updates view updates the hub from a git repository and each Mac's agent from the hub.

**The hub.** The hub updates itself from the repository it was installed from. Its update source is `update_url` and `update_branch` in its settings (see [Configuration](configuration.md)). The first `install.sh hub` from a clone records the clone's remote and the branch it follows there, and `cider-build hub-install` passes the remote and branch of the client's clone. Any git remote works: ssh, https or a local path, this project's repository or your fork.

Hub updates are off when `update_url` is `off`, and while it is unset, which happens when the hub was installed from a copy that is not a git clone. `off` is a decision that stays: reinstalls and hub updates never replace it. Unset is not, and the next install from a clone fills it in. With updates off, the hub never runs git, the Updates view says so and shows the command that turns them on, and `POST /hub/check` and `POST /hub/update` answer 409.

With a source, the hub keeps a bare copy of the branch in `~/cider-build/repo.git` and fetches it every 30 minutes (`update_check_s`) and on "Check for updates". It compares the files it runs (`install.sh` and `bin/`, fonts included) with the tip, and shows the branch's changelog: its last 30 changes on the branch's main line, newest first, each marked installed or pending. A GitHub merge commit or a squash merge shows as its PR's title and number. "Update hub" does this:
- Writes the new files to `~/cider-build/bin/.staged`.
- Compiles the Python files and runs `bash -n` on the scripts.
- Starts the new hub on the side, on scratch ports and a scratch folder with a copy of this hub's `hub.json`, until `/status` and the panel answer. A release that cannot read the hub's settings fails here.

If any step fails, nothing changes and the panel shows the error. Otherwise the hub copies its current files to `~/cider-build/bin/.previous` and swaps the new ones in. It waits for downloads and uploads in flight to finish, then exits, and launchd starts it on the new files. Builds on the Macs keep running, waiting clients keep polling, and agents retry their results. Updates never touch `hub.json`.

For an ssh `update_url`, `install.sh hub` creates `~/.ssh/cider-build-deploy` for the hub user (or reuses it, or the `~/.ssh/mac-build-deploy` of a hub from before the rename), sets `update_ssh_key` to it and prints its public key. Give that key read-only access to the repository on its git host, usually as a deploy key. Until then "Check for updates" fails, and the panel shows the ssh error next to the key. A public https repository or a local path needs no key.

To roll back, copy the previous files and `.commit` back from `.previous` and restart the hub. On the hub, as an administrator:

```bash
sudo -u <hub user> sh -c 'rm -f ~/cider-build/bin/.commit && cp -R ~/cider-build/bin/.previous/. ~/cider-build/bin/'
sudo launchctl kickstart -k system/com.cider-build.hub
```

**The agents.** The agent's version is a hash of `cider-build-worker` and `build.sh`, and the hub computes the same hash from the files it hands out at `/bin/`. Updating the hub therefore marks every agent outdated. "Update agent" on a Mac, or "Update all outdated", asks it to take no new builds. Once its running builds end, the agent downloads both files, checks the hash, compiles and parses them, swaps them in and exits, and launchd starts it again. If a step fails, it keeps its agent, the panel shows the error, and it retries every minute. Agents depend only on the hub, so they update the same way with hub updates off.

Agents installed before this feature cannot update themselves: the panel says to run `cider-build add <mac>` (or `/join` on the Mac) once. From then on the panel can update them.
