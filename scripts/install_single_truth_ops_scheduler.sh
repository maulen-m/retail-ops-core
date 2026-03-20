#!/bin/bash
# Install/update launchd schedulers for single-truth daily preflight and residual checks.
# Run: chmod +x scripts/install_single_truth_ops_scheduler.sh && ./scripts/install_single_truth_ops_scheduler.sh

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  scripts/install_single_truth_ops_scheduler.sh [--validate-only] [--project-dir <path>]

Options:
  --validate-only       Run fail-closed runtime checks only; do not load launchd jobs.
  --project-dir <path>  Override project root for validation/testing.
EOF
}

VALIDATE_ONLY=0
PROJECT_DIR_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --validate-only)
            VALIDATE_ONLY=1
            shift
            ;;
        --project-dir)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --project-dir requires a path" >&2
                exit 2
            fi
            PROJECT_DIR_OVERRIDE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [[ -n "$PROJECT_DIR_OVERRIDE" ]]; then
    PROJECT_DIR="$PROJECT_DIR_OVERRIDE"
fi
CHECK_ANCHOR_SCRIPT="$SCRIPT_DIR/check_anchor_health.py"
RENDER_PLISTS_SCRIPT="$SCRIPT_DIR/render_launchd_plists.py"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

PREFLIGHT_PLIST="com.example.single-truth-preflight.plist"
RESIDUALS_PLIST="com.example.on-delivery-residuals.plist"
ANCHOR_HEALTH_PLIST="com.example.anchor-health-warning.plist"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

echo "========================================"
echo "  Single-Truth Ops Scheduler Installation"
echo "========================================"
echo ""

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "FAIL: missing .venv/bin/python at $VENV_PYTHON" >&2
    exit 1
fi

if ! "$VENV_PYTHON" -c "import pandas; import requests; import openpyxl" >/dev/null 2>&1; then
    echo "FAIL: cannot import pandas/requests/openpyxl with $VENV_PYTHON" >&2
    exit 1
fi

echo "runtime checks passed: $VENV_PYTHON imports pandas/requests/openpyxl"

python3 "$RENDER_PLISTS_SCRIPT" --project-root "$PROJECT_DIR" --output-dir "$PROJECT_DIR/config/launchd_rendered" >/dev/null
echo "launchd templates rendered"

if [[ ! -f "$CHECK_ANCHOR_SCRIPT" ]]; then
    echo "FAIL: missing anchor health script at $CHECK_ANCHOR_SCRIPT" >&2
    exit 1
fi

if ! (cd "$PROJECT_DIR" && "$VENV_PYTHON" "$CHECK_ANCHOR_SCRIPT" --project-root "$PROJECT_DIR"); then
    echo "FAIL: anchor health check failed" >&2
    exit 1
fi

echo "anchor health checks passed"

if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
    echo "Validation-only mode complete."
    exit 0
fi

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

if launchctl list | grep -q "com.example.anchor-health-warning"; then
    echo "Unloading existing anchor-health scheduler..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$ANCHOR_HEALTH_PLIST" 2>/dev/null || true
fi

echo "Installing plists..."
cp "$PROJECT_DIR/config/$PREFLIGHT_PLIST" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/config/$RESIDUALS_PLIST" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/config/$ANCHOR_HEALTH_PLIST" "$LAUNCH_AGENTS_DIR/"

echo "Loading schedulers..."
launchctl load "$LAUNCH_AGENTS_DIR/$PREFLIGHT_PLIST"
launchctl load "$LAUNCH_AGENTS_DIR/$RESIDUALS_PLIST"
launchctl load "$LAUNCH_AGENTS_DIR/$ANCHOR_HEALTH_PLIST"

echo ""
echo "Single-truth schedulers installed successfully."
echo ""
echo "Schedules (local macOS time):"
echo "  - 20:55: anchor health check + optional alert"
echo "  - 21:00: strict preflight + lineage"
echo "  - 21:05: on-delivery residual dry-run + optional alert"
echo ""
echo "Anchor workbook expected at:"
echo "  - $PROJECT_DIR/config/anchors/SALES_KSP_CRM_LATEST.xlsx"
echo ""
echo "Status:"
launchctl list | grep "com.example.single-truth-preflight\\|com.example.on-delivery-residuals\\|com.example.anchor-health-warning" || echo "  (not yet running)"
echo ""
echo "To test manually:"
echo "  launchctl start com.example.anchor-health-warning"
echo "  launchctl start com.example.single-truth-preflight"
echo "  launchctl start com.example.on-delivery-residuals"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PREFLIGHT_PLIST"
echo "  launchctl unload ~/Library/LaunchAgents/$RESIDUALS_PLIST"
echo "  launchctl unload ~/Library/LaunchAgents/$ANCHOR_HEALTH_PLIST"
echo "  rm ~/Library/LaunchAgents/$PREFLIGHT_PLIST ~/Library/LaunchAgents/$RESIDUALS_PLIST ~/Library/LaunchAgents/$ANCHOR_HEALTH_PLIST"
