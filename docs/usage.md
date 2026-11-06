# Using cider-build

```bash
cider-build ios                 # in the project folder; the last line is the path of the .app
cider-build android ~/src/app   # the last line is the path of the .apk
cider-build status
CIDER_BUILD_FORCE=1 cider-build ios
cider-build warm                # starts the hub builds of this native version and returns right away
cider-build warm ios ~/src/app  # one platform only; both by default
```

`cider-build warm [ios] [android] [dir]` computes the cache key, submits it and uploads the source if the hub asks for it, then returns without waiting or downloading. It prints one line per platform: `already cached`, `queued (job <id>)` or `already building (job <id>)`; if the job was cancelled before its source arrived, it prints `cancelled on the hub (job <id>)` and exits 1. A later `cider-build ios` or `cider-build android` joins that build or downloads it from the hub cache. The hub keeps a warmed job even when a client that joined it presses Ctrl-C, and while its upload keeps arriving, however slow; only the panel's cancel stops it. A job whose source stops arriving for 2 minutes (the client crashed or the upload failed) is cancelled, warmed or not. Run it after a merge so the first developer does not wait for the whole build, for example with a git post-merge hook on `main`:

```bash
printf '#!/bin/sh\n[ "$(git branch --show-current)" = main ] && cider-build warm >/dev/null 2>&1 &\n' > .git/hooks/post-merge && chmod +x .git/hooks/post-merge
```

The first build of a project and platform uploads the whole project. After that, the client sends the hub a manifest (path, mode, mtime and sha256 of each file) and uploads only the files the hub does not have in that project's base tree, the files of its last upload. The hub rebuilds the whole source from both, checking every hash, before the job can be built, so the Macs receive the same thing as with a full upload. If the hub has no base, the base does not match its hashes or anything else fails, the client uploads the whole project, which becomes the new base. `CIDER_BUILD_FORCE=1` always uploads the whole project. The hub keeps one base per project and platform in `~/cider-build/bases/`, and deletes it after 7 days unused.

Ctrl-C stops waiting and cancels the build only if nobody else waits for it and nobody warmed it. The hub counts a client as waiting for 2 min after its last poll. So a client that gets no answer from the hub for 90 s gives up instead of waiting longer, with a message, and leaves the build running. That way another developer's Ctrl-C never cancels a build you are still waiting for. Running `cider-build` again joins the build or downloads it from the cache.

An upload may take as long as it needs: the hub never cancels a job while its source is still arriving. It cancels a job without source only once it has heard nothing of it for 2 minutes, counted from the request or from the end of the last upload, so a client that pressed Ctrl-C before uploading, crashed or failed its upload does not leave the job queued for anyone who joins it. An upload that receives nothing for 2 minutes is dropped.

Optional settings in the project's `.cider-build.json`: `ios.scheme`, `ios.workspace` or `ios.project`, `ios.configuration`, `android.task` and `android.apk`.
