#!/bin/bash
# install_launchagent.sh - Install/uninstall the End-of-Day LaunchAgent
#
# Usage:
#   ./scripts/install_launchagent.sh install   # Install and load the agent
#   ./scripts/install_launchagent.sh uninstall # Unload and remove the agent
#   ./scripts/install_launchagent.sh status    # Check agent status
#   ./scripts/install_launchagent.sh test      # Run the pipeline manually now

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLIST_SRC="$PROJECT_ROOT/config/com.inventory.endofday.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.inventory.endofday.plist"
LABEL="com.inventory.endofday"

case "$1" in
    install)
        echo "Installing LaunchAgent..."

        # Ensure logs directory exists
        mkdir -p "$PROJECT_ROOT/logs"

        # Unload if already loaded
        launchctl unload "$PLIST_DST" 2>/dev/null || true

        # Copy plist to LaunchAgents
        cp "$PLIST_SRC" "$PLIST_DST"

        # Load the agent
        launchctl load "$PLIST_DST"

        echo ""
        echo "LaunchAgent installed and loaded."
        echo "Schedule: Daily at 20:30 local time"
        echo ""
        echo "Logs:"
        echo "  stdout: $PROJECT_ROOT/logs/endofday.log"
        echo "  stderr: $PROJECT_ROOT/logs/endofday.err"
        echo ""
        echo "To verify: launchctl list | grep inventory"
        ;;

    uninstall)
        echo "Uninstalling LaunchAgent..."

        # Unload
        launchctl unload "$PLIST_DST" 2>/dev/null || true

        # Remove plist
        rm -f "$PLIST_DST"

        echo "LaunchAgent unloaded and removed."
        ;;

    status)
        echo "LaunchAgent Status:"
        echo ""
        if launchctl list | grep -q "$LABEL"; then
            launchctl list | grep "$LABEL"
            echo ""
            echo "Status: LOADED"
        else
            echo "Status: NOT LOADED"
        fi

        echo ""
        echo "Plist location: $PLIST_DST"
        if [ -f "$PLIST_DST" ]; then
            echo "Plist exists: YES"
        else
            echo "Plist exists: NO"
        fi

        echo ""
        echo "Recent logs:"
        if [ -f "$PROJECT_ROOT/logs/endofday.log" ]; then
            echo "--- Last 10 lines of stdout ---"
            tail -10 "$PROJECT_ROOT/logs/endofday.log"
        else
            echo "(no log file yet)"
        fi
        ;;

    test)
        echo "Running End-of-Day pipeline manually..."
        echo ""
        python3 "$PROJECT_ROOT/scripts/run_end_of_day.py" --verbose
        ;;

    *)
        echo "Usage: $0 {install|uninstall|status|test}"
        echo ""
        echo "Commands:"
        echo "  install   - Install and load the LaunchAgent"
        echo "  uninstall - Unload and remove the LaunchAgent"
        echo "  status    - Check if agent is loaded and show recent logs"
        echo "  test      - Run the pipeline manually now"
        exit 1
        ;;
esac
