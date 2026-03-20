#!/bin/bash
# Install/update launchd schedulers for Kaspi imports + waybill deadline run
# Run: chmod +x scripts/install_scheduler.sh && ./scripts/install_scheduler.sh

set -e

IMPORT_PLIST_NAME="com.example.kaspi-import.plist"
IMPORT_PLIST_DST_NAME="com.example.kaspi-import-v2.plist"
LEGACY_PLIST_NAME="com.example.kaspi-import.plist"
IMPORT_LABEL="com.example.kaspi-import-v2"
LEGACY_LABEL="com.example.kaspi-import"
WAYBILL_PLIST_NAME="com.example.kaspi-waybill-deadline.plist"
WAYBILL_LABEL="com.example.kaspi-waybill-deadline"
DAILY_REPORT_PLIST_NAME="com.example.kaspi-daily-ops-report.plist"
DAILY_REPORT_LABEL="com.example.kaspi-daily-ops-report"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
RENDER_SCRIPT="$PROJECT_DIR/scripts/render_launchd_plists.py"
RENDERED_PLIST_DIR="$PROJECT_DIR/config/launchd_rendered"
IMPORT_PLIST_SRC="$RENDERED_PLIST_DIR/$IMPORT_PLIST_NAME"
IMPORT_PLIST_DST="$LAUNCH_AGENTS_DIR/$IMPORT_PLIST_DST_NAME"
LEGACY_PLIST_DST="$LAUNCH_AGENTS_DIR/$LEGACY_PLIST_NAME"
WAYBILL_PLIST_SRC="$RENDERED_PLIST_DIR/$WAYBILL_PLIST_NAME"
WAYBILL_PLIST_DST="$LAUNCH_AGENTS_DIR/$WAYBILL_PLIST_NAME"
DAILY_REPORT_PLIST_SRC="$RENDERED_PLIST_DIR/$DAILY_REPORT_PLIST_NAME"
DAILY_REPORT_PLIST_DST="$LAUNCH_AGENTS_DIR/$DAILY_REPORT_PLIST_NAME"
RUNTIME_LOG_DIR="$PROJECT_DIR/runtime_logs"
GUI_DOMAIN="gui/$(id -u)"

echo "========================================"
echo "  Kaspi Import Scheduler Installation"
echo "========================================"
echo ""

# Create directories
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$RUNTIME_LOG_DIR"

python3 "$RENDER_SCRIPT" --project-root "$PROJECT_DIR" --output-dir "$RENDERED_PLIST_DIR" >/dev/null

# Boot out if already loaded
if launchctl print "$GUI_DOMAIN/$IMPORT_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing import scheduler..."
    launchctl bootout "$GUI_DOMAIN/$IMPORT_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$WAYBILL_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing waybill deadline scheduler..."
    launchctl bootout "$GUI_DOMAIN/$WAYBILL_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$DAILY_REPORT_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing daily ops report scheduler..."
    launchctl bootout "$GUI_DOMAIN/$DAILY_REPORT_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$LEGACY_LABEL" >/dev/null 2>&1; then
    echo "Unloading legacy scheduler label..."
    launchctl bootout "$GUI_DOMAIN/$LEGACY_LABEL" 2>/dev/null || true
fi
if [ -f "$LEGACY_PLIST_DST" ]; then
    rm -f "$LEGACY_PLIST_DST"
fi

# Copy plist to LaunchAgents
echo "Installing import scheduler plist..."
cp "$IMPORT_PLIST_SRC" "$IMPORT_PLIST_DST"
echo "Installing waybill deadline scheduler plist..."
cp "$WAYBILL_PLIST_SRC" "$WAYBILL_PLIST_DST"
echo "Installing daily ops report scheduler plist..."
cp "$DAILY_REPORT_PLIST_SRC" "$DAILY_REPORT_PLIST_DST"

# Load and explicitly enable the scheduler
echo "Loading import scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$IMPORT_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$IMPORT_LABEL" 2>/dev/null || true
echo "Loading waybill deadline scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$WAYBILL_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$WAYBILL_LABEL" 2>/dev/null || true
echo "Loading daily ops report scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$DAILY_REPORT_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$DAILY_REPORT_LABEL" 2>/dev/null || true

echo ""
echo "Schedulers installed successfully!"
echo ""
echo "Schedule (local Asia/Almaty):"
echo "  - 11:00 - Import (daily)"
echo "  - 16:03 - Import (daily)"
echo "  - 18:30 - Waybill deadline run (daily)"
echo "  - 19:10 - Daily ops report (daily)"
echo ""
echo "Logs will be written to:"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stderr.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_waybill_deadline_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_waybill_deadline_stderr.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_daily_ops_report_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_daily_ops_report_stderr.log"
echo ""
echo "Status:"
launchctl print "$GUI_DOMAIN/$IMPORT_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (import scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$WAYBILL_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (waybill scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$DAILY_REPORT_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (daily report scheduler not yet running)"
echo ""
echo "To test manually:"
echo "  launchctl kickstart -k $GUI_DOMAIN/$IMPORT_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$WAYBILL_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$DAILY_REPORT_LABEL"
echo ""
echo "To uninstall:"
echo "  launchctl bootout $GUI_DOMAIN/$IMPORT_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$WAYBILL_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$DAILY_REPORT_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$LEGACY_LABEL"
echo "  rm ~/Library/LaunchAgents/$IMPORT_PLIST_DST_NAME"
echo "  rm ~/Library/LaunchAgents/$WAYBILL_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$DAILY_REPORT_PLIST_NAME"
