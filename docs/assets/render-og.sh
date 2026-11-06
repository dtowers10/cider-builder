#!/usr/bin/env bash
# Renders docs/assets/og.html to docs/assets/og.png (2400x1260, 2x of 1200x630) with headless Chrome.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
chrome=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}
"$chrome" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --window-size=1200,630 --force-device-scale-factor=2 --virtual-time-budget=2000 \
  --screenshot="$dir/og.png" "file://$dir/og.html" 2>/dev/null
echo "$dir/og.png"
