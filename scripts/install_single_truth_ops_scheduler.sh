#!/bin/bash
# Install/update launchd schedulers for single-truth daily preflight and residual checks.
# Run: chmod +x scripts/install_single_truth_ops_scheduler.sh && ./scripts/install_single_truth_ops_scheduler.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

PREFLIGHT_PLIST="com.example.single-truth-preflight.plist"
RESIDUALS_PLIST="com.example.on-delivery-residuals.plist"

echo "========================================"
echo "  Single-Truth Ops Scheduler Installation"
echo "========================================"
echo ""

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/config/anchors"

if launchctl list | grep -q "com.example.single-truth-preflight"; then
    echo "Unloading existing preflight scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$PREFLIGHT_PLIST" 2>/dev/null || true
fi

if launchctl list | grep -q "com.example.on-delivery-residuals"; then
    echo "Unloading existing residual scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$RESIDUALS_PLIST" 2>/dev/null || true
fi

echo "Installing plists..."
cp "$PROJECT_DIR/config/$PREFLIGHT_PLIST" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/config/$RESIDUALS_PLIST" "$LAUNCH_AGENTS_DIR/"

echo "Loading schedulers..."
launchctl load "$LAUNCH_AGENTS_DIR/$PREFLIGHT_PLIST"
launchctl load "$LAUNCH_AGENTS_DIR/$RESIDUALS_PLIST"

echo ""
echo "Single-truth schedulers installed successfully."
echo ""
echo "Schedules (local macOS time):"
echo "  - 21:00: strict preflight + lineage"
echo "  - 21:05: on-delivery residual dry-run + optional alert"
echo ""
echo "Anchor workbook expected at:"
echo "  - $PROJECT_DIR/config/anchors/SALES_KSP_CRM_LATEST.xlsx"
echo ""
echo "Status:"
launchctl list | grep "com.example.single-truth-preflight\\|com.example.on-delivery-residuals" || echo "  (not yet running)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.single-truth-preflight"
echo "  launchctl start com.example.on-delivery-residuals"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PREFLIGHT_PLIST"
echo "  launchctl unload ~/Library/LaunchAgents/$RESIDUALS_PLIST"
echo "  rm ~/Library/LaunchAgents/$PREFLIGHT_PLIST ~/Library/LaunchAgents/$RESIDUALS_PLIST"
