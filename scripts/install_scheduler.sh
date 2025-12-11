#!/bin/bash
# Install/update launchd scheduler for Kaspi imports
# Run: chmod +x scripts/install_scheduler.sh && ./scripts/install_scheduler.sh

set -e

PLIST_NAME="com.example.kaspi-import.plist"
PROJECT_DIR="~/Docs/Autonomous_business"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "========================================"
echo "  Kaspi Import Scheduler Installation"
echo "========================================"
echo ""

# Create directories
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"

# Unload if already loaded
if launchctl list | grep -q "com.example.kaspi-import"; then
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
echo "Schedule:"
echo "  - 11:00 GMT+5 (06:00 UTC) - First import"
echo "  - 16:00 GMT+5 (11:00 UTC) - Second import"
echo ""
echo "Logs will be written to:"
echo "  - $PROJECT_DIR/logs/import_stdout.log"
echo "  - $PROJECT_DIR/logs/import_stderr.log"
echo ""
echo "Status:"
launchctl list | grep kaspi || echo "  (not yet running, will start at scheduled time)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.kaspi-import"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$PLIST_NAME"
