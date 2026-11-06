---
name: cider-build
description: Build an iOS simulator .app or an Android .apk of the current project on the team's Mac fleet with the `cider-build` CLI. Use when asked to build, compile, or run an Expo, React Native, Xcode, or Gradle app, or to get a fresh .app or .apk to install on a simulator or emulator.
---

# Build on the Mac fleet

`cider-build` sends the project to a hub, a Mac builds it, and the artifact comes back to this machine. It works from Linux, so it replaces a local `xcodebuild` or `gradlew` run. Builds of a native version that already exists come from the cache in seconds.

## Steps

1. **Check the client.** Run `cider-build hub`. Done when it prints a URL. If the command is missing or it exits 2, tell the user to install the client from their hub: `curl -fsSL https://<hub>:4710/bin/install.sh | bash -s client`. Stop there.
2. **Prepare an Expo or React Native project.** Its cache key needs node and an installed `node_modules`. Done when `node_modules/` exists. Otherwise install the dependencies with the project's package manager first.
3. **Build.** In the project folder, run `cider-build ios` or `cider-build android`, in the background or with a timeout of at least 30 minutes. A cold build takes minutes, and a cache hit takes seconds. Progress and the build log go to stderr. Let the command run to its exit. An interrupted command cancels the build when nobody else waits for it. Done when the command exits.
4. **Read the result.** On exit 0, the last line of stdout is the artifact path. For iOS it is a simulator `.app` folder, and for Android an `.apk`. Done when you have that path. Report it, or install it with `xcrun simctl install <device> <path>` or `adb install -r <path>` when the user wants it running.

## Failures

The message before the exit names the cause:

- `The build failed on <mac> (exit code N)`: the project failed to build. The build log above it on stderr has the compiler or Gradle error. Fix the project and build again.
- `No ios project recognized` or `No android project recognized` (exit 2): run the command in the app's root folder, the one with `package.json`, the `.xcodeproj`, or `gradlew`.
- `Could not compute the fingerprint`: step 2 is missing.
- `The hub has not answered for 90 s`: the build goes on without the client. Run the same command again to join it or download its result.
- `Cannot talk to the hub`: the hub is unreachable from this machine. Run `cider-build status`, and report what it prints to the user.

## Options

- `cider-build warm` starts both builds on the hub and returns at once. Use it ahead of a later build.
- `CIDER_BUILD_FORCE=1` rebuilds from scratch and uploads the whole project. Use it only when the user asks for a clean build.
- A `.cider-build.json` in the project sets the iOS scheme, the workspace or project, the configuration, the Gradle task, and the APK path. `cider-build --help` lists every command and setting.
