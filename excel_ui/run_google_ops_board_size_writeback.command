#!/bin/bash
# Write back MY_SIZE edits from Google Ops Board into db/app.db.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
source .venv/bin/activate 2>/dev/null || true

SERVICE_JSON="${AB_GOOGLE_SERVICE_ACCOUNT_JSON:-~/Docs/Business/S/ab-ops-board-sync-key.json}"

echo "========================================"
echo "  Google Ops Board Size Writeback"
echo "========================================"
echo ""

python3 scripts/check_local_app_db.py --db-path "${PROJECT_ROOT}/db/app.db"
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: local DB preflight failed."
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

if [ ! -f "${SERVICE_JSON}" ]; then
    echo ""
    echo "ERROR: Google service-account JSON missing: ${SERVICE_JSON}"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

AB_GOOGLE_SERVICE_ACCOUNT_JSON="${SERVICE_JSON}" \
PYTHONUNBUFFERED=1 \
python3 -u scripts/sync_google_ops_board_sizes_to_db.py \
    --target-date "$(date +%Y-%m-%d)" \
    --service-account-json "${SERVICE_JSON}"
RC=$?

echo ""
if [ ${RC} -ne 0 ]; then
    echo "ERROR: Google Ops Board size writeback failed."
else
    echo "Google Ops Board size preview complete. Final DB writeback runs only inside the READY-bound closeout."
fi
echo ""
echo "Press Enter to close..."
[[ -t 0 ]] && read
exit ${RC}
