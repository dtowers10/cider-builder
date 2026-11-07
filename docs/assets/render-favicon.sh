#!/usr/bin/env bash
# Renders docs/assets/favicon.svg to the PNG sizes (32, 180 apple-touch, 512) with headless Chrome.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
chrome=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for size in 32 180 512; do
  printf '<style>*{margin:0}html,body{background:transparent}</style><img src="file://%s/favicon.svg" width="%s" height="%s" style="display:block">' "$dir" "$size" "$size" > "$tmp/f.html"
  "$chrome" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files --default-background-color=00000000 \
    --window-size="$size,$size" --screenshot="$dir/favicon-$size.png" "file://$tmp/f.html" 2>/dev/null
  echo "$dir/favicon-$size.png"
done
