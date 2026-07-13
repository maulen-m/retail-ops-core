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
GOOGLE_BOARD_PUBLISH_PLIST_NAME="com.example.google-ops-board-publish.plist"
GOOGLE_BOARD_PUBLISH_LABEL="com.example.google-ops-board-publish"
GOOGLE_BOARD_PREWINDOW_PLIST_NAME="com.example.google-ops-board-prewindow-health.plist"
GOOGLE_BOARD_PREWINDOW_LABEL="com.example.google-ops-board-prewindow-health"
GOOGLE_BOARD_WRITEBACK_PLIST_NAME="com.example.google-ops-board-size-writeback.plist"
GOOGLE_BOARD_WRITEBACK_LABEL="com.example.google-ops-board-size-writeback"
GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_NAME="com.example.google-ops-board-closeout-watch.plist"
GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL="com.example.google-ops-board-closeout-watch"
GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_NAME="com.example.google-ops-board-closeout-caffeinate.plist"
GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL="com.example.google-ops-board-closeout-caffeinate"
WAYBILL_TELEGRAM_CONTROL_PLIST_NAME="com.example.waybill-telegram-control.plist"
WAYBILL_TELEGRAM_CONTROL_LABEL="com.example.waybill-telegram-control"
KASPI_SHIPPED_TRUTH_SYNC_PLIST_NAME="com.example.kaspi-shipped-truth-sync.plist"
KASPI_SHIPPED_TRUTH_SYNC_LABEL="com.example.kaspi-shipped-truth-sync"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
IMPORT_PLIST_SRC="$PROJECT_DIR/config/$IMPORT_PLIST_NAME"
IMPORT_PLIST_DST="$LAUNCH_AGENTS_DIR/$IMPORT_PLIST_DST_NAME"
LEGACY_PLIST_DST="$LAUNCH_AGENTS_DIR/$LEGACY_PLIST_NAME"
WAYBILL_PLIST_SRC="$PROJECT_DIR/config/$WAYBILL_PLIST_NAME"
WAYBILL_PLIST_DST="$LAUNCH_AGENTS_DIR/$WAYBILL_PLIST_NAME"
DAILY_REPORT_PLIST_SRC="$PROJECT_DIR/config/$DAILY_REPORT_PLIST_NAME"
DAILY_REPORT_PLIST_DST="$LAUNCH_AGENTS_DIR/$DAILY_REPORT_PLIST_NAME"
GOOGLE_BOARD_PUBLISH_PLIST_SRC="$PROJECT_DIR/config/$GOOGLE_BOARD_PUBLISH_PLIST_NAME"
GOOGLE_BOARD_PUBLISH_PLIST_DST="$LAUNCH_AGENTS_DIR/$GOOGLE_BOARD_PUBLISH_PLIST_NAME"
GOOGLE_BOARD_PREWINDOW_PLIST_SRC="$PROJECT_DIR/config/$GOOGLE_BOARD_PREWINDOW_PLIST_NAME"
GOOGLE_BOARD_PREWINDOW_PLIST_DST="$LAUNCH_AGENTS_DIR/$GOOGLE_BOARD_PREWINDOW_PLIST_NAME"
GOOGLE_BOARD_WRITEBACK_PLIST_SRC="$PROJECT_DIR/config/$GOOGLE_BOARD_WRITEBACK_PLIST_NAME"
GOOGLE_BOARD_WRITEBACK_PLIST_DST="$LAUNCH_AGENTS_DIR/$GOOGLE_BOARD_WRITEBACK_PLIST_NAME"
GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_SRC="$PROJECT_DIR/config/$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_NAME"
GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_DST="$LAUNCH_AGENTS_DIR/$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_NAME"
GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_SRC="$PROJECT_DIR/config/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_NAME"
GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_DST="$LAUNCH_AGENTS_DIR/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_NAME"
WAYBILL_TELEGRAM_CONTROL_PLIST_SRC="$PROJECT_DIR/config/$WAYBILL_TELEGRAM_CONTROL_PLIST_NAME"
WAYBILL_TELEGRAM_CONTROL_PLIST_DST="$LAUNCH_AGENTS_DIR/$WAYBILL_TELEGRAM_CONTROL_PLIST_NAME"
KASPI_SHIPPED_TRUTH_SYNC_PLIST_SRC="$PROJECT_DIR/config/$KASPI_SHIPPED_TRUTH_SYNC_PLIST_NAME"
KASPI_SHIPPED_TRUTH_SYNC_PLIST_DST="$LAUNCH_AGENTS_DIR/$KASPI_SHIPPED_TRUTH_SYNC_PLIST_NAME"
RUNTIME_LOG_DIR="$PROJECT_DIR/runtime_logs"
GUI_DOMAIN="gui/$(id -u)"

echo "========================================"
echo "  Kaspi + Google Ops Board Scheduler Installation"
echo "========================================"
echo ""

# Create directories
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$RUNTIME_LOG_DIR"

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
if launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Google Ops Board publish scheduler..."
    launchctl bootout "$GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Google Ops Board prewindow health scheduler..."
    launchctl bootout "$GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Google Ops Board size writeback scheduler..."
    launchctl bootout "$GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Google Ops Board closeout watch scheduler..."
    launchctl bootout "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Google Ops Board closeout caffeinate scheduler..."
    launchctl bootout "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing waybill Telegram control scheduler..."
    launchctl bootout "$GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL" 2>/dev/null || true
fi
if launchctl print "$GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL" >/dev/null 2>&1; then
    echo "Unloading existing Kaspi shipped-truth sync scheduler..."
    launchctl bootout "$GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL" 2>/dev/null || true
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
echo "Installing Google Ops Board publish scheduler plist..."
cp "$GOOGLE_BOARD_PUBLISH_PLIST_SRC" "$GOOGLE_BOARD_PUBLISH_PLIST_DST"
echo "Installing Google Ops Board prewindow health scheduler plist..."
cp "$GOOGLE_BOARD_PREWINDOW_PLIST_SRC" "$GOOGLE_BOARD_PREWINDOW_PLIST_DST"
echo "Installing Google Ops Board size writeback scheduler plist..."
cp "$GOOGLE_BOARD_WRITEBACK_PLIST_SRC" "$GOOGLE_BOARD_WRITEBACK_PLIST_DST"
echo "Installing Google Ops Board closeout watch scheduler plist..."
cp "$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_SRC" "$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_DST"
echo "Installing Google Ops Board closeout caffeinate scheduler plist..."
cp "$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_SRC" "$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_DST"
echo "Installing waybill Telegram control scheduler plist..."
cp "$WAYBILL_TELEGRAM_CONTROL_PLIST_SRC" "$WAYBILL_TELEGRAM_CONTROL_PLIST_DST"
echo "Installing Kaspi shipped-truth sync scheduler plist..."
cp "$KASPI_SHIPPED_TRUTH_SYNC_PLIST_SRC" "$KASPI_SHIPPED_TRUTH_SYNC_PLIST_DST"

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
echo "Loading Google Ops Board publish scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$GOOGLE_BOARD_PUBLISH_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL" 2>/dev/null || true
echo "Loading Google Ops Board prewindow health scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$GOOGLE_BOARD_PREWINDOW_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL" 2>/dev/null || true
echo "Loading Google Ops Board size writeback scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$GOOGLE_BOARD_WRITEBACK_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL" 2>/dev/null || true
echo "Loading Google Ops Board closeout watch scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL" 2>/dev/null || true
echo "Loading Google Ops Board closeout caffeinate scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL" 2>/dev/null || true
echo "Loading waybill Telegram control scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$WAYBILL_TELEGRAM_CONTROL_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL" 2>/dev/null || true
echo "Loading Kaspi shipped-truth sync scheduler..."
launchctl bootstrap "$GUI_DOMAIN" "$KASPI_SHIPPED_TRUTH_SYNC_PLIST_DST"
launchctl enable "$GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL" 2>/dev/null || true

echo ""
echo "Schedulers installed successfully!"
echo ""
echo "Schedule (local Asia/Almaty):"
echo "  - 11:00 - Import (daily)"
echo "  - immediate after successful import - Google Ops Board publish"
echo "  - 07:00 - Google Ops Board full source refresh + publish"
echo "  - 11:00 - Google Ops Board quiet publish"
echo "  - 13:45 - Google Ops Board prewindow health + identity sync"
echo "  - 14:01 to 17:11 every 10 minutes - Google Ops Board publish backstop (fails closed if ActiveOrders is stale for target date)"
echo "  - 15:02 - Import (daily)"
echo "  - 16:01 - Import (daily)"
echo "  - 17:02 - Import (17:00 all-store late-window DB freshness / next-day visibility)"
echo "  - 17:15, 17:30, 17:45, 18:00, 18:15 - Google Ops Board size-writeback preview (read-only)"
echo "  - 18:20 - Google Ops Board closeout caffeinate keep-awake guard"
echo "  - every 15s between 09:00 and 24:00 (script-gated, 60s READY debounce; 18:57 probable-size auto-fill) - Google Ops Board early-ready closeout watch"
echo "  - 18:30 - Google Ops Board closeout backstop (ship -> waybills -> build -> send)"
echo "  - 09:30 and 19:15 - Kaspi shipped-truth DB sync"
echo "  - every 15s - Telegram /ready fallback control"
echo "  - 19:10 - Daily ops report (daily)"
echo ""
echo "Logs will be written to:"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_import_stderr.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_waybill_deadline_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_waybill_deadline_stderr.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_daily_ops_report_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_daily_ops_report_stderr.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_publish_stdout.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_publish_stderr.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_prewindow_health_stdout.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_prewindow_health_stderr.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_size_writeback_stdout.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_size_writeback_stderr.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_closeout_watch_stdout.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_closeout_watch_stderr.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_shipped_truth_sync_stdout.log"
echo "  - $RUNTIME_LOG_DIR/kaspi_shipped_truth_sync_stderr.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_closeout_caffeinate_stdout.log"
echo "  - $RUNTIME_LOG_DIR/google_ops_board_closeout_caffeinate_stderr.log"
echo "  - $RUNTIME_LOG_DIR/waybill_telegram_control_stdout.log"
echo "  - $RUNTIME_LOG_DIR/waybill_telegram_control_stderr.log"
echo ""
echo "Status:"
launchctl print "$GUI_DOMAIN/$IMPORT_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (import scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$WAYBILL_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (waybill scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$DAILY_REPORT_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (daily report scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Google Ops Board publish scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Google Ops Board prewindow health scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Google Ops Board size writeback scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Google Ops Board closeout watch scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Google Ops Board closeout caffeinate scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (waybill Telegram control scheduler not yet running)"
launchctl print "$GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL" | grep -E "state =|last exit code|runs =" || echo "  (Kaspi shipped-truth sync scheduler not yet running)"
echo ""
echo "To test manually:"
echo "  launchctl kickstart -k $GUI_DOMAIN/$IMPORT_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$WAYBILL_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$DAILY_REPORT_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL"
echo "  launchctl kickstart -k $GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL"
echo ""
echo "To uninstall:"
echo "  launchctl bootout $GUI_DOMAIN/$IMPORT_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$WAYBILL_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$DAILY_REPORT_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$GOOGLE_BOARD_PUBLISH_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$GOOGLE_BOARD_PREWINDOW_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$GOOGLE_BOARD_WRITEBACK_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_WATCH_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$WAYBILL_TELEGRAM_CONTROL_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$KASPI_SHIPPED_TRUTH_SYNC_LABEL"
echo "  launchctl bootout $GUI_DOMAIN/$LEGACY_LABEL"
echo "  rm ~/Library/LaunchAgents/$IMPORT_PLIST_DST_NAME"
echo "  rm ~/Library/LaunchAgents/$WAYBILL_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$DAILY_REPORT_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$GOOGLE_BOARD_PUBLISH_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$GOOGLE_BOARD_PREWINDOW_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$GOOGLE_BOARD_WRITEBACK_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$GOOGLE_BOARD_CLOSEOUT_WATCH_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$GOOGLE_BOARD_CLOSEOUT_CAFFEINATE_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$WAYBILL_TELEGRAM_CONTROL_PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$KASPI_SHIPPED_TRUTH_SYNC_PLIST_NAME"
