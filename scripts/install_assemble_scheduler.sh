#!/bin/bash
# Install/update launchd scheduler for daily Kaspi assembly.
# Run: chmod +x scripts/install_assemble_scheduler.sh && ./scripts/install_assemble_scheduler.sh

set -e

PLIST_NAME="com.example.kaspi-assemble.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "========================================"
echo "  Kaspi Assembly Scheduler Installation"
echo "========================================"
echo ""

# Create directories
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"

# Unload if already loaded
if launchctl list | grep -q "com.example.kaspi-assemble"; then
    echo "Unloading existing scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
echo "Installing plist..."
cp "$PROJECT_DIR/config/$PLIST_NAME" "$LAUNCH_AGENTS_DIR/"

# Load the scheduler
echo "Loading scheduler..."
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo ""
echo "Scheduler installed successfully!"
echo ""
echo "Schedule: Daily at 16:10 local time (GMT+5 desired)"
echo "Note: LaunchAgent uses macOS local time; set system TZ to GMT+5 if needed."
echo ""
echo "Logs will be written to:"
echo "  - $PROJECT_DIR/logs/assemble_stdout.log"
echo "  - $PROJECT_DIR/logs/assemble_stderr.log"
echo ""
echo "Status:"
launchctl list | grep kaspi-assemble || echo "  (not yet running, will start at scheduled time)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.kaspi-assemble"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$PLIST_NAME"
