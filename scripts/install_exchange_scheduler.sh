#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.example.exchange-import.plist"
PLIST_SRC="$ROOT_DIR/config/$PLIST_NAME"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

mkdir -p "$LAUNCH_AGENTS_DIR"

if launchctl list | grep -q "com.example.exchange-import"; then
  launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"

echo "Installed exchange import scheduler:"
echo "  $PLIST_DST"
echo "Verify:"
echo "  launchctl list | grep exchange-import"
