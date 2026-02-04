#!/bin/bash
# Install/update launchd scheduler for daily Kaspi marketing ads scrape.
# Run: chmod +x scripts/install_kaspi_marketing_scheduler.sh && ./scripts/install_kaspi_marketing_scheduler.sh

set -e

PLIST_NAME="com.example.kaspi-marketing-ads.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "========================================"
echo "  Kaspi Marketing Scheduler Installation"
echo "========================================"
echo ""

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"

if launchctl list | grep -q "com.example.kaspi-marketing-ads"; then
    echo "Unloading existing scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true
fi

echo "Installing plist..."
cp "$PROJECT_DIR/config/$PLIST_NAME" "$LAUNCH_AGENTS_DIR/"

echo "Loading scheduler..."
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo ""
echo "Scheduler installed successfully!"
echo ""
echo "Schedule: Daily at 20:30 local time (GMT+5 desired)"
echo "Note: LaunchAgent uses macOS local time; set system TZ to GMT+5 if needed."
echo ""
echo "Logs will be written to:"
echo "  - $PROJECT_DIR/logs/marketing_stdout.log"
echo "  - $PROJECT_DIR/logs/marketing_stderr.log"
echo ""
echo "Status:"
launchctl list | grep kaspi-marketing-ads || echo "  (not yet running, will start at scheduled time)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.kaspi-marketing-ads"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$PLIST_NAME"
