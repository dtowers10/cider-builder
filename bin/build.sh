#!/bin/bash
# Builds a project on this Mac. cider-build-worker launches it with the source already unpacked in $STAGE.
# Input (environment): KIND PLAT PROJ KEY OUT STAGE EXCL MB_SCHEME MB_CONTAINER MB_CONFIG MB_TASK MB_APK.
# Output: $OUT, which the agent picks per attempt. The log is standard output (the agent stores it).
set -euo pipefail
export PATH=/opt/homebrew/bin:/opt/homebrew/opt/openjdk@17/bin:/usr/bin:/bin:/usr/sbin:/sbin
export LANG=en_US.UTF-8 CI=1 EXPO_NO_TELEMETRY=1 COCOAPODS_DISABLE_STATS=1
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME=$HOME/Library/Android/sdk ANDROID_SDK_ROOT=$HOME/Library/Android/sdk
B=$HOME/builds
src=$B/src/$PROJ-$PLAT dd=$B/dd/$PROJ out=$OUT
mkdir -p "$src" "$dd" "$(dirname "$out")"
lock=$B/.lock-$PROJ-$PLAT
until mkdir "$lock" 2>/dev/null; do
  pid=$(cat "$lock/pid" 2>/dev/null || true)
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$lock"; continue; fi
  echo "Waiting for another build of $PROJ ($PLAT) on this Mac…"; sleep 15
done
echo $$ >"$lock/pid"; trap 'rm -rf "$lock"' EXIT
# Excluded paths are not deleted from the destination: node_modules, Pods and build/ survive between builds.
set -f; ex=(); for e in $EXCL; do ex+=(--exclude "$e"); done; set +f
rsync -a --delete "${ex[@]}" "$STAGE/" "$src/"
cd "$src"

deps() { # node_modules is reused as long as package.json and the lockfile do not change
  local h stamp=$B/src/.deps-$PROJ-$PLAT
  h=$({ cat package.json package-lock.json yarn.lock pnpm-lock.yaml bun.lock bun.lockb 2>/dev/null || true; } | shasum | cut -c1-40)
  if [ -d node_modules ] && [ "$(cat "$stamp" 2>/dev/null)" = "$h" ]; then return 0; fi
  if [ -f pnpm-lock.yaml ]; then corepack pnpm install --frozen-lockfile
  elif [ -f yarn.lock ]; then corepack yarn install --immutable 2>/dev/null || corepack yarn install --frozen-lockfile
  elif [ -f bun.lock ] || [ -f bun.lockb ]; then bun install --frozen-lockfile
  else npm ci --no-audit --no-fund; fi
  echo "$h" >"$stamp"
}
xcode() { # [-workspace X | -project Y] (or nothing for Package.swift); scheme from MB_SCHEME or the first one
  local scheme=$MB_SCHEME app
  [ -n "$scheme" ] || scheme=$(xcodebuild -list -json "$@" | /usr/bin/python3 -c '
import json, sys
j = json.load(sys.stdin); print((j.get("workspace") or j.get("project") or {}).get("schemes", [""])[0])')
  xcodebuild "$@" -scheme "$scheme" -configuration "$MB_CONFIG" -sdk iphonesimulator \
    -destination 'generic/platform=iOS Simulator' -derivedDataPath "$dd" ARCHS=arm64 \
    CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO -quiet
  app=$(ls -td "$dd/Build/Products/$MB_CONFIG-iphonesimulator/"*.app | head -1)
  tar -czf "$out.tmp" -C "$(dirname "$app")" "$(basename "$app")"
}
apk() { local f; f=$(ls -t $1 | head -1); cp "$f" "$out.tmp"; }
rn_native() {
  if [ "$PLAT" = ios ]; then
    (cd ios && pod install)
    local ws=${MB_CONTAINER:-$(ls -d ios/*.xcworkspace | head -1)}
    MB_SCHEME=${MB_SCHEME:-$(basename "$ws" .xcworkspace)} xcode -workspace "$ws"
  else
    (cd android && ./gradlew "$MB_TASK" -PreactNativeArchitectures=arm64-v8a --build-cache --console=plain)
    apk "${MB_APK:-android/app/build/outputs/apk/debug/*.apk}"
  fi
}
build_expo() { deps; npx expo prebuild --platform "$PLAT" --clean --no-install; rn_native; }
build_react_native() { deps; rn_native; }
build_ios_native() {
  local c=$MB_CONTAINER
  if [ -f Podfile ]; then pod install; fi
  if [ -z "$c" ]; then for c in ./*.xcworkspace ./*.xcodeproj ""; do [ -e "$c" ] && break; done; fi
  case $c in *.xcworkspace) xcode -workspace "$c" ;; *.xcodeproj) xcode -project "$c" ;; *) xcode ;; esac
}
build_android_native() { chmod +x gradlew; ./gradlew "$MB_TASK" --console=plain; apk "${MB_APK:-*/build/outputs/apk/debug/*.apk}"; }

echo "Building $PROJ ($PLAT, ${KIND}) on $(hostname -s)…"
trap 'echo "cider-build: failed: ${BASH_COMMAND}"' ERR
set -E
"build_$KIND"
mv "$out.tmp" "$out"
