#!/bin/bash
# FAST Kaspi import: API → Excel → CRM (no status updates)
# Downloads TODAY's pending orders from Kaspi API, imports to CRM
# For status updates, use run_status_update.command separately
# Double-click to run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
source .venv/bin/activate 2>/dev/null || true
if [ -f ".env" ]; then
    ENV_EXPORTS=$(python3 - <<'PY'
import re
import shlex
from pathlib import Path

p = Path(".env")
if not p.exists():
    raise SystemExit(0)

SHELL_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("GMAIL_"):
        continue
    if "=" not in line:
        continue
    key, val = line.split("=", 1)
    key = key.strip()
    if not key:
        continue
    if not SHELL_KEY_RE.match(key):
        continue
    print(f"export {key}={shlex.quote(val.strip())}")
PY
)
    if [ -n "${ENV_EXPORTS}" ]; then
        eval "${ENV_EXPORTS}"
    fi
fi

if [ -z "${AB_DATA_DIR:-}" ] && [ -z "${DATA_DIR:-}" ]; then
    export DATA_DIR="${PROJECT_ROOT}"
fi
DATA_ROOT="${AB_DATA_DIR:-${DATA_DIR:-${PROJECT_ROOT}}}"

run_excel_session_preflight() {
    local label="${1:-Preflight: validating Excel session state...}"
    echo ""
    echo "${label}"
    echo "----------------------------------------"
    python3 scripts/import_orders_to_crm.py --excel-session-preflight-only
}

read_import_summary_fields() {
    local summary_path="${1}"
    if [ ! -f "${summary_path}" ]; then
        return 0
    fi
    SUMMARY_PATH="${summary_path}" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["SUMMARY_PATH"])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

status = str(payload.get("status") or "")
retryable_topup = "1" if bool(payload.get("retryable_topup", False)) else "0"
print(status)
print(retryable_topup)
PY
}

echo "Preflight: validating local app DB..."
echo "----------------------------------------"
python3 scripts/check_local_app_db.py --db-path "${PROJECT_ROOT}/db/app.db"
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: local DB preflight failed."
    echo "Fix: ensure db/app.db is a local regular SQLite file (not iCloud symlink/dataless)."
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi
echo ""

if [ -z "${AB_GDRIVE_KASPI_SALES_PATH:-}" ]; then
    export AB_GDRIVE_KASPI_SALES_PATH="${HOME}/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business/Shared/Kaspi/Kaspi orders/Kaspi_drive_sales_v1.xlsx"
fi

DEFAULT_LOOKBACK_DAYS=5
LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS:-${DEFAULT_LOOKBACK_DAYS}}"

INCLUDE_OVERDUE="${KASPI_INCLUDE_OVERDUE:-1}"
DATE_FLAG=""
if [ "${INCLUDE_OVERDUE}" = "1" ]; then
    DATE_FLAG="--include-overdue"
fi
IMPORT_DATE_FLAGS=""
if [ "${INCLUDE_OVERDUE}" = "1" ]; then
    IMPORT_DATE_FLAGS="--include-overdue --overdue-lookback-days ${LOOKBACK_DAYS}"
fi

REFRESH_DELIVERY_FEES="${KASPI_REFRESH_DELIVERY_FEES:-1}"
REFRESH_FEES_FROM=$(date -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)
REFRESH_FEES_TO=$(date +%Y-%m-%d)
REFRESH_DELIVERY_FLAGS=""
FIXED_BACKFILL_FLAGS="--fixed-backfill-from ${REFRESH_FEES_FROM} --fixed-backfill-to ${REFRESH_FEES_TO}"
if [ "${REFRESH_DELIVERY_FEES}" = "1" ]; then
    REFRESH_DELIVERY_FLAGS="--refresh-delivery-fees --refresh-fees-from ${REFRESH_FEES_FROM} --refresh-fees-to ${REFRESH_FEES_TO}"
fi

WARNINGS=()
HARD_FAIL=0
HARD_FAIL_REASONS=()
ACTIVEORDERS_SNAPSHOT=""
LATE_ARRIVAL_RETRY_MAX="${KASPI_LATE_ARRIVAL_RETRY_MAX:-2}"

echo "========================================"
echo "  FAST Kaspi Order Import"
echo "  (no archive fetch, no status updates)"
echo "========================================"
echo ""
echo "Lookback days: ${LOOKBACK_DAYS}"
echo ""

# Step 1: Download pending orders for TODAY (no archive for speed)
echo "Step 1: Downloading TODAY's pending orders from Kaspi API..."
echo "----------------------------------------"
python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days "${LOOKBACK_DAYS}" ${DATE_FLAG} --refetch-missing-costs --verbose --no-archive

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: API export failed!"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

# Ensure MELVIS rows are present (fallback fetch + merge if missing)
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    HAS_MELVIS=$(python3 - <<'PY'
import pandas as pd
from pathlib import Path
p = Path("excel_ui/ActiveOrders/ActiveOrders.xlsx")
try:
    df = pd.read_excel(p)
except Exception:
    print("0")
    raise SystemExit(0)

col = None
for c in ("Склад передачи КД", "STORE_NAME", "Склад передачи КД"):
    if c in df.columns:
        col = c
        break

if not col:
    print("0")
else:
    vals = df[col].astype(str)
    has_code = (vals == "30362323_PP1").any()
    has_name = vals.str.contains(r"\bMELVIS\b|\bStore-C\b", regex=True, na=False).any()
    print("1" if (has_code or has_name) else "0")
PY
)
    if [ "${HAS_MELVIS}" = "0" ]; then
        if [ -n "${KASPI_TOKEN_MELVIS:-}" ]; then
            echo "MELVIS rows not found in ActiveOrders. Fetching MELVIS..."
            TMP_DIR=$(mktemp -d -t kaspi_store-c_import)
            MELVIS_OUT="${TMP_DIR}/ActiveOrders_MELVIS.xlsx"
            python scripts/export_api_orders.py --store MELVIS --state KASPI_DELIVERY --days "${LOOKBACK_DAYS}" --refetch-missing-costs --verbose --no-archive --output "${MELVIS_OUT}"
            MELVIS_RC=$?
            if [ -f "${MELVIS_OUT}" ]; then
                MELVIS_ROWS=$(MELVIS_OUT="${MELVIS_OUT}" python3 - <<'PY'
import os
from pathlib import Path
import pandas as pd

p = Path(os.environ.get("MELVIS_OUT", ""))
if not p.exists():
    print(0)
    raise SystemExit(0)
try:
    df = pd.read_excel(p)
except Exception:
    print(-1)
    raise SystemExit(0)
print(len(df))
PY
)
            else
                MELVIS_ROWS=0
            fi
            if [ "${MELVIS_RC}" -eq 0 ] && [ -f "${MELVIS_OUT}" ] && [ "${MELVIS_ROWS}" -gt 0 ]; then
                MELVIS_OUT="${MELVIS_OUT}" python3 - <<'PY'
import pandas as pd
from pathlib import Path
import os
base = Path("excel_ui/ActiveOrders/ActiveOrders.xlsx")
store-c_path = os.environ.get("MELVIS_OUT", "")
store-c = Path(store-c_path) if store-c_path else None
if store-c and base.exists() and store-c.exists():
    df_base = pd.read_excel(base)
    df_store-c = pd.read_excel(store-c)
    merged = pd.concat([df_base, df_store-c], ignore_index=True).drop_duplicates()
    merged.to_excel(base, index=False, engine='openpyxl')
    print(f"Merged MELVIS rows: +{len(df_store-c)} (deduped to {len(merged)})")
PY
            elif [ "${MELVIS_RC}" -eq 0 ]; then
                echo "No MELVIS rows found for filter; continuing."
            else
                echo "WARNING: MELVIS export failed or missing output."
                WARNINGS+=("MELVIS export failed or missing output. Fix: check KASPI_TOKEN_MELVIS and API connectivity.")
            fi
            rm -rf "${TMP_DIR}"
        else
            echo "WARNING: KASPI_TOKEN_MELVIS not set; skipping MELVIS fetch."
            WARNINGS+=("MELVIS token missing; MELVIS fetch skipped.")
        fi
    fi
fi

# Quick sanity check on exported ActiveOrders
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    python - <<'PY'
import pandas as pd
from pathlib import Path
p = Path("excel_ui/ActiveOrders/ActiveOrders.xlsx")
try:
    df = pd.read_excel(p)
    print(f"ActiveOrders rows: {len(df)}")
    if len(df) == 0:
        raise SystemExit(2)
except Exception:
    raise SystemExit(3)
PY
    RC=$?
    if [ $RC -eq 2 ]; then
        echo "WARNING: ActiveOrders.xlsx has 0 rows after export."
        WARNINGS+=("ActiveOrders export returned 0 rows. Fix: check Kaspi planned date filter or API connectivity.")
    elif [ $RC -eq 3 ]; then
        echo "WARNING: ActiveOrders.xlsx could not be read."
        WARNINGS+=("ActiveOrders.xlsx unreadable. Fix: re-export or open/save the file.")
    fi
fi

# Preflight: SKU prefix parse sanity check (Артикул → SKU_key)
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    echo ""
    echo "Preflight: SKU prefix parse sanity check..."
    echo "----------------------------------------"
    python - <<'PY'
import pandas as pd
from core.parsers.kaspi_parser import extract_sku_from_article

path = "excel_ui/ActiveOrders/ActiveOrders.xlsx"
df = pd.read_excel(path)
if "Артикул" not in df.columns:
    print("ActiveOrders: no Артикул column; skipping SKU parse check.")
    raise SystemExit(0)

offer_col = "Название товара в Kaspi Магазине"
offers = df[offer_col] if offer_col in df.columns else [None] * len(df)

total = len(df)
mapped = 0
for article, offer in zip(df["Артикул"], offers):
    parsed = extract_sku_from_article(article, offer)
    if parsed.get("sku_key"):
        mapped += 1

rate = (mapped / total) if total else 0
print(f"SKU parsed: {mapped}/{total} ({rate:.0%})")
if total > 0 and rate < 0.7:
    print("WARNING: Low SKU parse rate. Check Артикул formatting / SKU prefix rule.")
PY
    if [ $? -ne 0 ]; then
        echo "WARNING: SKU parse sanity check failed."
        WARNINGS+=("SKU parse sanity check failed. Fix: verify Артикул format or parser logic.")
    fi
fi

# Step 1b: Sync DB from API (order lifecycle)
echo ""
echo "Step 1b: Syncing DB from API..."
echo "----------------------------------------"
SINCE_DATE=$(date -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)
python scripts/sync_kaspi_orders.py --all --since "$SINCE_DATE"
if [ $? -ne 0 ]; then
    echo "WARNING: API -> DB sync failed (see above)."
    WARNINGS+=("API -> DB sync failed. Fix: check tokens/network, then re-run.")
fi
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    echo "Preflight: checking ActiveOrders columns..."
    python scripts/validate_activeorders_columns.py excel_ui/ActiveOrders/ActiveOrders.xlsx
    if [ $? -ne 0 ]; then
        echo "WARNING: ActiveOrders columns mismatch (see above)."
        WARNINGS+=("ActiveOrders columns mismatch. Fix: re-export ActiveOrders from Kaspi.")
    fi
else
    echo "WARNING: ActiveOrders.xlsx not found; CRM import may be incomplete."
    WARNINGS+=("ActiveOrders.xlsx missing. Fix: re-run export_api_orders step.")
fi

# Preflight: CRM workbook integrity check (hard gate)
echo ""
echo "Preflight: validating CRM workbook integrity..."
echo "----------------------------------------"
INTEGRITY_ALLOW_EXACT=(
    "named range contains #REF!: B"
    "named range contains #REF!: B_DAYS"
    "named range contains #REF!: D"
    "named range contains #REF!: D_AFTER"
    "named range contains #REF!: L"
    "named range contains #REF!: L_DAYS"
    "named range contains #REF!: SS_TOTAL"
    "named range contains #REF!: T_POST"
    "named range contains #REF!: TV"
    "named range contains #REF!: TV_FLOOR"
    "named range contains #REF!: Z"
    "named range contains #REF!: Z_LEVEL"
)
INTEGRITY_ALLOW_PREFIX=(
    # Some legacy date-scoped names can be regenerated by Excel as broken refs
    # (e.g. _02.12.2025). They do not affect import data integrity.
    "named range contains #REF!: _"
)
VALIDATE_CMD=(
    python3 scripts/validate_crm_workbook_integrity.py
    --workbook excel_ui/SALES_KSP_CRM_V3.xlsx
    --repair-missing-shared-strings
    --repair-backup-dir excel_ui/backups
)
for allowed_error in "${INTEGRITY_ALLOW_EXACT[@]}"; do
    VALIDATE_CMD+=(--allow-error-exact "${allowed_error}")
done
for allowed_prefix in "${INTEGRITY_ALLOW_PREFIX[@]}"; do
    VALIDATE_CMD+=(--allow-error-prefix "${allowed_prefix}")
done
"${VALIDATE_CMD[@]}"
if [ $? -ne 0 ]; then
    echo "ERROR: CRM workbook integrity validation failed."
    echo "Fix workbook first, then re-run import."
    echo "Suggested repair command:"
    echo "  python3 scripts/repair_crm_workbook.py --workbook excel_ui/SALES_KSP_CRM_V3.xlsx --apply"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

if ! run_excel_session_preflight "Preflight: validating Excel session state before CRM import..."; then
    echo ""
    echo "ERROR: Excel session preflight failed."
    echo "Fix: close SALES_KSP_CRM_V3.xlsx in Excel, then re-run full import."
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

# Step 2: Import new orders to CRM (also updates existing order status columns)
echo ""
echo "Step 2: Importing new orders to CRM..."
echo "----------------------------------------"
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    ACTIVEORDERS_SNAPSHOT=$(mktemp -t activeorders_snapshot_XXXXXX.xlsx)
    if cp "excel_ui/ActiveOrders/ActiveOrders.xlsx" "${ACTIVEORDERS_SNAPSHOT}"; then
        echo "Captured ActiveOrders snapshot for success gate: ${ACTIVEORDERS_SNAPSHOT}"
    else
        echo "WARNING: failed to snapshot ActiveOrders; strict gate will use API-vs-CRM report."
        WARNINGS+=("ActiveOrders snapshot failed. Fix: check temp dir permissions.")
        rm -f "${ACTIVEORDERS_SNAPSHOT}" 2>/dev/null || true
        ACTIVEORDERS_SNAPSHOT=""
    fi
else
    echo "WARNING: ActiveOrders.xlsx missing before Step 2; snapshot gate disabled."
    WARNINGS+=("ActiveOrders missing before Step 2. Fix: re-run export step.")
fi

STEP2_TIMEOUT_SEC="${CRM_IMPORT_TIMEOUT_SEC:-900}"
XLWINGS_OPEN_TIMEOUT_SEC="${CRM_XLWINGS_OPEN_TIMEOUT_SEC:-45}"
XLWINGS_APPEND_TIMEOUT_SEC="${CRM_XLWINGS_APPEND_TIMEOUT_SEC:-420}"
SUMMARY_PATH="logs/import_orders_to_crm_latest.json"
rm -f "${SUMMARY_PATH}" 2>/dev/null || true
# This command intentionally skips existing-row status updates for unattended runs.
STEP2_NO_UPDATE=1
echo "Step 2 timeout: ${STEP2_TIMEOUT_SEC}s"
echo "xlwings open timeout: ${XLWINGS_OPEN_TIMEOUT_SEC}s"
echo "xlwings append timeout: ${XLWINGS_APPEND_TIMEOUT_SEC}s"
CRM_XLWINGS_APPEND_TIMEOUT_SEC="${XLWINGS_APPEND_TIMEOUT_SEC}" \
CRM_XLWINGS_OPEN_TIMEOUT_SEC="${XLWINGS_OPEN_TIMEOUT_SEC}" \
python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \
    python scripts/import_orders_to_crm.py \
        --verbose \
        --no-update \
        --strict-excel \
        --kaspi-core-override \
        ${IMPORT_DATE_FLAGS} \
        ${REFRESH_DELIVERY_FLAGS} \
        ${FIXED_BACKFILL_FLAGS} \
        --no-gdrive-sync
STEP2_RC=$?
STEP2_WARN_MSG=""
STEP2_STATUS=""
STEP2_RETRYABLE_TOPUP=0
STEP2_SKIP_DOWNSTREAM=0
SUMMARY_FIELDS=$(read_import_summary_fields "${SUMMARY_PATH}")
if [ -n "${SUMMARY_FIELDS}" ]; then
    STEP2_STATUS=$(printf '%s\n' "${SUMMARY_FIELDS}" | sed -n '1p')
    STEP2_RETRYABLE_TOPUP=$(printf '%s\n' "${SUMMARY_FIELDS}" | sed -n '2p')
fi
if [ ${STEP2_RC} -ne 0 ]; then
    echo "WARNING: CRM import reported errors (see above)."
    if [ "${STEP2_STATUS}" = "preflight_blocked" ]; then
        STEP2_WARN_MSG="CRM import blocked by CRM workbook conflict. Fix: close SALES_KSP_CRM_V3.xlsx in Excel, then re-run."
    elif [ "${STEP2_STATUS}" = "append_verification_failed" ]; then
        STEP2_WARN_MSG="CRM import append verification failed. Fix: inspect import_orders_to_crm.py --verbose before rerun."
    elif [ ${STEP2_RC} -eq 124 ]; then
        STEP2_WARN_MSG="CRM import timed out after ${STEP2_TIMEOUT_SEC}s. Fix: close Excel and re-run."
    else
        STEP2_WARN_MSG="CRM import errors. Fix: open CRM and re-run import_orders_to_crm.py --verbose."
    fi
    if [ "${STEP2_RETRYABLE_TOPUP}" != "1" ]; then
        STEP2_SKIP_DOWNSTREAM=1
        HARD_FAIL=1
        HARD_FAIL_REASONS+=("CRM import failed before a retryable append state (${STEP2_STATUS:-unknown}).")
    fi
fi

# Determine if import produced any changes (used to skip expensive retry steps)
IMPORT_NOOP=0
if [ -f "${SUMMARY_PATH}" ]; then
    IMPORT_NOOP=$(python - <<'PY'
import json
from pathlib import Path
path = Path("logs/import_orders_to_crm_latest.json")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    payload = {}
imported = int(payload.get("orders_imported", 0) or 0)
updated = int(payload.get("orders_updated", 0) or 0)
print(1 if imported == 0 and updated == 0 else 0)
PY
)
fi

# Step 2c: Enforce canonical Line61 Kaspi_name_core for existing historical rows
echo ""
echo "Step 2c: Backfilling Line61 Kaspi_name_core..."
echo "----------------------------------------"
if [ "${STEP2_SKIP_DOWNSTREAM}" = "1" ]; then
    echo "NO-OP: skipping Line61 Kaspi_name_core backfill (Step 2 did not reach a safe write-complete state)."
elif [ "${IMPORT_NOOP}" -eq 1 ]; then
    echo "NO-OP: skipping Line61 Kaspi_name_core backfill (no CRM changes)."
else
    python3 scripts/backfill_line61_kaspi_core.py \
        --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
        --sheet SALES_KSP_CRM_1 \
        --table tb_SalesRaw \
        --backup-dir excel_ui/backups \
        --apply
    if [ $? -ne 0 ]; then
        echo "WARNING: Line61 Kaspi_name_core backfill failed (see above)."
        WARNINGS+=("Line61 Kaspi_name_core backfill failed. Fix: run scripts/backfill_line61_kaspi_core.py manually.")
    fi
fi

# Step 2b: Validate pending orders alignment (CRM vs DB/ActiveOrders)
echo ""
echo "Step 2b: Validating pending orders..."
echo "----------------------------------------"
if [ "${STEP2_SKIP_DOWNSTREAM}" = "1" ]; then
    echo "NO-OP: skipping pending order validation (Step 2 did not reach a safe write-complete state)."
elif [ "${STEP2_NO_UPDATE}" = "1" ]; then
    echo "NO-OP: skipping pending order validation in --no-update mode."
elif [ "${IMPORT_NOOP}" -eq 1 ]; then
    echo "NO-OP: skipping pending order validation (no CRM changes)."
else
    PENDING_ARGS=""
    if [ "${INCLUDE_OVERDUE}" = "1" ]; then
        PENDING_ARGS="--include-overdue --lookback-days ${LOOKBACK_DAYS}"
    fi
    python scripts/validate_pending_orders.py ${PENDING_ARGS}
    if [ $? -ne 0 ]; then
        echo "WARNING: Pending order validation reported mismatches (see above)"
        WARNINGS+=("Pending order validation mismatches. Fix: check ActiveOrders export + CRM planned date column.")
    fi
fi

# Post-import health report (API vs CRM vs DB)
echo ""
echo "Post-import health report..."
echo "----------------------------------------"
HEALTH_JSON=""
if [ "${STEP2_SKIP_DOWNSTREAM}" = "1" ]; then
    echo "NO-OP: skipping post-import health report (Step 2 did not reach a safe write-complete state)."
else
    HEALTH_JSON=$(mktemp -t kaspi_import_health)
    python3 scripts/report_import_status.py --since-days "${LOOKBACK_DAYS}" --json-out "${HEALTH_JSON}"
    if [ $? -ne 0 ]; then
        echo "WARNING: Post-import health report failed."
        WARNINGS+=("Post-import health report failed. Fix: run scripts/report_import_status.py manually.")
        HARD_FAIL=1
        HARD_FAIL_REASONS+=("Post-import health report command failed.")
    fi

    LATE_ARRIVAL_RETRY_COUNT=0
    while [ "${HARD_FAIL}" -eq 0 ] && [ -f "${HEALTH_JSON}" ]; do
        HEALTH_COUNTS=$(HEALTH_JSON="${HEALTH_JSON}" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["HEALTH_JSON"])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("-1 -1")
    raise SystemExit(0)
totals = payload.get("totals", {})
try:
    miss_crm = int(totals.get("miss_crm", 0) or 0)
    stale_crm = int(totals.get("stale_crm", 0) or 0)
    print(f"{miss_crm} {stale_crm}")
except Exception:
    print("-1 -1")
PY
)
        MISS_CRM=$(printf '%s\n' "${HEALTH_COUNTS}" | awk '{print $1}')
        STALE_CRM=$(printf '%s\n' "${HEALTH_COUNTS}" | awk '{print $2}')
        if [ "${MISS_CRM}" = "-1" ]; then
            echo "WARNING: unable to parse miss_crm/stale_crm from post-import health report."
            WARNINGS+=("Unable to parse miss_crm/stale_crm from post-import health report. Fix: inspect ${HEALTH_JSON}.")
            HARD_FAIL=1
            HARD_FAIL_REASONS+=("Post-import health JSON parse failed.")
            break
        fi
        if [ -z "${MISS_CRM}" ] || [ "${MISS_CRM}" -le 0 ]; then
            if [ -n "${STALE_CRM}" ] && [ "${STALE_CRM}" -gt 0 ]; then
                :
            else
                break
            fi
        fi
        if [ -z "${STALE_CRM}" ]; then
            STALE_CRM=0
        fi
        if [ "${MISS_CRM}" -le 0 ] && [ "${STALE_CRM}" -le 0 ]; then
            break
        fi
        if [ "${LATE_ARRIVAL_RETRY_COUNT}" -ge "${LATE_ARRIVAL_RETRY_MAX}" ]; then
            if [ "${MISS_CRM}" -gt 0 ]; then
                echo "WARNING: Post-import health still reports ${MISS_CRM} live API orders missing in CRM after ${LATE_ARRIVAL_RETRY_COUNT} late-arrival top-up pass(es)."
                WARNINGS+=("Post-import health still reports ${MISS_CRM} live API orders missing in CRM after ${LATE_ARRIVAL_RETRY_COUNT} late-arrival top-up pass(es). Fix: rerun full import or inspect live API arrivals.")
            fi
            if [ "${STALE_CRM}" -gt 0 ]; then
                echo "WARNING: Post-import health still reports ${STALE_CRM} stale today rows in CRM after ${LATE_ARRIVAL_RETRY_COUNT} late-arrival top-up pass(es)."
                WARNINGS+=("Post-import health still reports ${STALE_CRM} stale today rows in CRM after ${LATE_ARRIVAL_RETRY_COUNT} late-arrival top-up pass(es). Fix: rerun full import or inspect today CRM block.")
            fi
            break
        fi

        LATE_ARRIVAL_RETRY_COUNT=$((LATE_ARRIVAL_RETRY_COUNT + 1))
        echo ""
        echo "Late-arrival top-up pass ${LATE_ARRIVAL_RETRY_COUNT}/${LATE_ARRIVAL_RETRY_MAX}..."
        echo "----------------------------------------"
        if [ "${MISS_CRM}" -gt 0 ]; then
            echo "Post-import health found ${MISS_CRM} live API orders missing in CRM."
        fi
        if [ "${STALE_CRM}" -gt 0 ]; then
            echo "Post-import health found ${STALE_CRM} stale today rows in CRM."
        fi
        echo "Re-exporting ActiveOrders and rerunning CRM import."

        if ! run_excel_session_preflight "Preflight: validating Excel session state before late-arrival top-up..."; then
            echo "WARNING: late-arrival top-up blocked by Excel session preflight."
            WARNINGS+=("Late-arrival top-up blocked by Excel session preflight. Fix: close SALES_KSP_CRM_V3.xlsx in Excel, then rerun full import.")
            HARD_FAIL=1
            HARD_FAIL_REASONS+=("Late-arrival top-up blocked by Excel session preflight.")
            break
        fi

        python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days "${LOOKBACK_DAYS}" ${DATE_FLAG} --refetch-missing-costs --verbose --no-archive
        if [ $? -ne 0 ]; then
            echo "WARNING: late-arrival top-up export failed."
            WARNINGS+=("Late-arrival top-up export failed. Fix: rerun full import.")
            HARD_FAIL=1
            HARD_FAIL_REASONS+=("Late-arrival top-up export failed.")
            break
        fi

        if [ -n "${ACTIVEORDERS_SNAPSHOT}" ] && [ -f "${ACTIVEORDERS_SNAPSHOT}" ]; then
            rm -f "${ACTIVEORDERS_SNAPSHOT}" 2>/dev/null || true
        fi
        ACTIVEORDERS_SNAPSHOT=$(mktemp -t activeorders_snapshot_XXXXXX.xlsx)
        if cp "excel_ui/ActiveOrders/ActiveOrders.xlsx" "${ACTIVEORDERS_SNAPSHOT}"; then
            echo "Refreshed ActiveOrders snapshot for success gate: ${ACTIVEORDERS_SNAPSHOT}"
        else
            echo "WARNING: failed to refresh ActiveOrders snapshot during late-arrival top-up."
            WARNINGS+=("Late-arrival top-up snapshot failed. Fix: check temp dir permissions.")
            rm -f "${ACTIVEORDERS_SNAPSHOT}" 2>/dev/null || true
            ACTIVEORDERS_SNAPSHOT=""
        fi

        rm -f "${SUMMARY_PATH}" 2>/dev/null || true
        CRM_XLWINGS_APPEND_TIMEOUT_SEC="${XLWINGS_APPEND_TIMEOUT_SEC}" \
        CRM_XLWINGS_OPEN_TIMEOUT_SEC="${XLWINGS_OPEN_TIMEOUT_SEC}" \
        python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \
            python scripts/import_orders_to_crm.py \
                --verbose \
                --no-update \
                --strict-excel \
                --kaspi-core-override \
                ${IMPORT_DATE_FLAGS} \
                ${REFRESH_DELIVERY_FLAGS} \
                ${FIXED_BACKFILL_FLAGS} \
                --no-gdrive-sync
        TOPUP_STEP2_RC=$?
        if [ ${TOPUP_STEP2_RC} -ne 0 ]; then
            echo "WARNING: late-arrival top-up CRM import reported errors (see above)."
            if [ ${TOPUP_STEP2_RC} -eq 124 ]; then
                WARNINGS+=("Late-arrival top-up CRM import timed out after ${STEP2_TIMEOUT_SEC}s. Fix: close Excel and re-run.")
            else
                WARNINGS+=("Late-arrival top-up CRM import errors. Fix: rerun import_orders_to_crm.py --verbose.")
            fi
            STEP2_RC=${TOPUP_STEP2_RC}
            HARD_FAIL=1
            HARD_FAIL_REASONS+=("Late-arrival top-up CRM import failed.")
            break
        fi
        STEP2_RC=0
        STEP2_WARN_MSG=""

        python3 scripts/backfill_line61_kaspi_core.py \
            --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
            --sheet SALES_KSP_CRM_1 \
            --table tb_SalesRaw \
            --backup-dir excel_ui/backups \
            --apply
        if [ $? -ne 0 ]; then
            echo "WARNING: Line61 Kaspi_name_core backfill failed after late-arrival top-up (see above)."
            WARNINGS+=("Line61 Kaspi_name_core backfill failed after late-arrival top-up. Fix: run scripts/backfill_line61_kaspi_core.py manually.")
        fi

        rm -f "${HEALTH_JSON}" 2>/dev/null || true
        HEALTH_JSON=$(mktemp -t kaspi_import_health)
        python3 scripts/report_import_status.py --since-days "${LOOKBACK_DAYS}" --json-out "${HEALTH_JSON}"
        if [ $? -ne 0 ]; then
            echo "WARNING: Post-import health report failed after late-arrival top-up."
            WARNINGS+=("Post-import health report failed after late-arrival top-up. Fix: run scripts/report_import_status.py manually.")
            HARD_FAIL=1
            HARD_FAIL_REASONS+=("Post-import health report failed after late-arrival top-up.")
            break
        fi
    done
fi

if [ -n "${STEP2_WARN_MSG}" ]; then
    WARNINGS+=("${STEP2_WARN_MSG}")
fi

echo ""
echo "Final success gate..."
echo "----------------------------------------"
if [ "${STEP2_SKIP_DOWNSTREAM}" = "1" ]; then
    echo "NO-OP: skipping final success gate (Step 2 did not reach a safe write-complete state)."
else
    EVAL_CMD=(
        python3 scripts/evaluate_import_run_result.py
        --step2-rc "${STEP2_RC}"
        --health-json "${HEALTH_JSON}"
    )
    if [ -n "${ACTIVEORDERS_SNAPSHOT}" ] && [ -f "${ACTIVEORDERS_SNAPSHOT}" ]; then
        EVAL_CMD+=(
            --activeorders-file "${ACTIVEORDERS_SNAPSHOT}"
            --crm-file "excel_ui/SALES_KSP_CRM_V3.xlsx"
            --target-date "$(date +%Y-%m-%d)"
        )
    fi
    "${EVAL_CMD[@]}"
    GATE_RC=$?
    if [ ${GATE_RC} -ne 0 ]; then
        HARD_FAIL=1
        HARD_FAIL_REASONS+=("Strict success gate failed (Step2 failure or API/CRM mismatch).")
    fi
fi
rm -f "${HEALTH_JSON}" "${ACTIVEORDERS_SNAPSHOT}" 2>/dev/null || true

# Step 3: Google Drive sync
echo ""
echo "Step 3: Google Drive sync skipped in unattended mode (--no-gdrive-sync)"
echo "----------------------------------------"
echo "Note: CRM append is prioritized for reliability; run scripts/sync_to_gdrive.py manually if needed."

echo ""
echo "========================================"
echo "  Done!"
echo "========================================"
echo ""
echo "For status updates (Завершен, Отменен, Возвращен):"
echo "  Run: run_status_update.command"
if [ ${#WARNINGS[@]} -ne 0 ]; then
    echo ""
    echo "Warnings summary:"
    for w in "${WARNINGS[@]}"; do
        echo "  - ${w}"
    done
fi
if [ "${HARD_FAIL}" -ne 0 ]; then
    echo ""
    echo "ERROR: strict success gate failed."
    if [ ${#HARD_FAIL_REASONS[@]} -ne 0 ]; then
        echo "Hard failure reasons:"
        for reason in "${HARD_FAIL_REASONS[@]}"; do
            echo "  - ${reason}"
        done
    fi
    echo ""
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi
echo ""
echo "Press Enter to close..."
[[ -t 0 ]] && read
exit 0
