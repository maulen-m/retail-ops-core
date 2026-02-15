#!/bin/bash
# Install/update launchd scheduler for Kaspi imports
# Run: chmod +x scripts/install_scheduler.sh && ./scripts/install_scheduler.sh

set -e

PLIST_NAME="com.example.kaspi-import.plist"
PLIST_DST_NAME="com.example.kaspi-import-v2.plist"
LEGACY_PLIST_NAME="com.example.kaspi-import.plist"
LABEL="com.example.kaspi-import-v2"
LEGACY_LABEL="com.example.kaspi-import"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_SRC="$PROJECT_DIR/config/$PLIST_NAME"
PLIST_DST="$LAUNCH_AGENTS_DIR/$PLIST_DST_NAME"
LEGACY_PLIST_DST="$LAUNCH_AGENTS_DIR/$LEGACY_PLIST_NAME"
RUNTIME_LOG_DIR="$PROJECT_DIR/runtime_logs"
GUI_DOMAIN="gui/$(id -u)"

echo "========================================"
echo "  Kaspi Import Scheduler Installation"
echo "========================================"
echo ""

# Create directories
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$RUNTIME_LOG_DIR"

# Boot out if already loaded
if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "Unloading existing scheduler..."
    launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$LEGACY_LABEL" >/dev/null 2>&1; then
    echo "Unloading legacy scheduler label..."
    launchctl bootout "$GUI_DOMAIN/$LEGACY_LABEL" 2>/dev/null || true
fi
if [ -f "$LEGACY_PLIST_DST" ]; then
    rm -f "$LEGACY_PLIST_DST"
fi

# Copy plist to LaunchAgents
echo "Installing plist..."
cp "$PLIST_SRC" "$PLIST_DST"

# Load and explicitly enable the scheduler
echo "Loading scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_DST"
launchctl enable "$GUI_DOMAIN/$LABEL" 2>/dev/null || true

echo ""
echo "Scheduler installed successfully!"
echo ""
echo "Schedule (local Asia/Almaty):"
echo "  - 10:30 - Import (lookback 5 days)"
echo "  - 15:02 - Import (lookback 5 days)"
echo "  - 20:30 - Import (lookback 14 days)"
echo ""
echo "Logs will be written to:"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stderr.log"
echo ""
echo "Status:"
launchctl print "$GUI_DOMAIN/$LABEL" | grep -E "state =|last exit code|runs =" || echo "  (not yet running, starts at schedule)"
echo ""
echo "To test manually:"
echo "  launchctl kickstart -k $GUI_DOMAIN/$LABEL"
echo ""
echo "To uninstall:"
echo "  launchctl bootout $GUI_DOMAIN/$LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$LEGACY_LABEL"
echo "  rm ~/Library/LaunchAgents/$PLIST_DST_NAME"
