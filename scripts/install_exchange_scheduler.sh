#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLISTS=(
  "com.example.exchange-import.plist"
  "com.example.gmail-pubsub.plist"
  "com.example.gmail-watch-refresh.plist"
)

LEGACY_LABELS=(
  "com.transferledger.autopilot"
  "com.example.gmail-pubsub-listener"
)

mkdir -p "$LAUNCH_AGENTS_DIR"

for plist in "${PLISTS[@]}"; do
  if launchctl list | grep -q "${plist%.plist}"; then
    launchctl unload "$LAUNCH_AGENTS_DIR/$plist" 2>/dev/null || true
  fi
done

for label in "${LEGACY_LABELS[@]}"; do
  launchctl remove "$label" 2>/dev/null || true
  rm -f "$LAUNCH_AGENTS_DIR/$label.plist"
done

for plist in "${PLISTS[@]}"; do
  src="$ROOT_DIR/config/$plist"
  dst="$LAUNCH_AGENTS_DIR/$plist"
  if [[ ! -f "$src" ]]; then
    echo "Skip missing: $src"
    continue
  fi
  cp "$src" "$dst"
  launchctl load "$dst"
done

echo "Installed exchange + gmail schedulers:"
for plist in "${PLISTS[@]}"; do
  echo "  $LAUNCH_AGENTS_DIR/$plist"
done
echo "Verify:"
echo "  launchctl list | grep exchange-import"
