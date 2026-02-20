#!/bin/bash
# Install/update launchd scheduler for daily External_database backup.
# Run: chmod +x scripts/install_external_database_backup_scheduler.sh && ./scripts/install_external_database_backup_scheduler.sh

set -e

PLIST_NAME="com.example.external-database-backup.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "========================================"
echo "  External Database Backup Installation"
echo "========================================"
echo ""

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"

if launchctl list | grep -q "com.example.external-database-backup"; then
    echo "Unloading existing scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true
fi

echo "Installing plist..."
cp "$PROJECT_DIR/config/$PLIST_NAME" "$LAUNCH_AGENTS_DIR/"

echo "Loading scheduler..."
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo ""
echo "Scheduler installed successfully!"
echo "Schedule: Daily at 21:10 local time"
echo ""
echo "Logs:"
echo "  - $PROJECT_DIR/logs/external_db_backup_stdout.log"
echo "  - $PROJECT_DIR/logs/external_db_backup_stderr.log"
echo ""
echo "Status:"
launchctl list | grep external-database-backup || echo "  (not yet running, starts at schedule)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.external-database-backup"
