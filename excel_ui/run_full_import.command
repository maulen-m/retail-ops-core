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
import shlex
from pathlib import Path

p = Path(".env")
if not p.exists():
    raise SystemExit(0)

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

WARNINGS=()

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
VALIDATE_CMD=(
    python3 scripts/validate_crm_workbook_integrity.py
    --workbook excel_ui/SALES_KSP_CRM_V3.xlsx
    --repair-missing-shared-strings
    --repair-backup-dir excel_ui/backups
)
for allowed_error in "${INTEGRITY_ALLOW_EXACT[@]}"; do
    VALIDATE_CMD+=(--allow-error-exact "${allowed_error}")
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

# Step 2: Import new orders to CRM (also updates existing order status columns)
echo ""
echo "Step 2: Importing new orders to CRM..."
echo "----------------------------------------"
STEP2_TIMEOUT_SEC="${CRM_IMPORT_TIMEOUT_SEC:-900}"
XLWINGS_OPEN_TIMEOUT_SEC="${CRM_XLWINGS_OPEN_TIMEOUT_SEC:-45}"
XLWINGS_APPEND_TIMEOUT_SEC="${CRM_XLWINGS_APPEND_TIMEOUT_SEC:-420}"
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
        --no-transactional \
        --no-strict-excel \
        --kaspi-core-override \
        --no-gdrive-sync \
        --skip-fixed-backfill
STEP2_RC=$?
if [ ${STEP2_RC} -ne 0 ]; then
    echo "WARNING: CRM import reported errors (see above)."
    if [ ${STEP2_RC} -eq 124 ]; then
        WARNINGS+=("CRM import timed out after ${STEP2_TIMEOUT_SEC}s. Fix: close Excel and re-run.")
    else
        WARNINGS+=("CRM import errors. Fix: open CRM and re-run import_orders_to_crm.py --verbose.")
    fi
fi

# Determine if import produced any changes (used to skip expensive retry steps)
IMPORT_NOOP=0
SUMMARY_PATH="logs/import_orders_to_crm_latest.json"
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
if [ "${IMPORT_NOOP}" -eq 1 ]; then
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
if [ "${STEP2_NO_UPDATE}" = "1" ]; then
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
if [ "${IMPORT_NOOP}" -eq 1 ]; then
    echo "NO-OP: skipping health report (no CRM changes)."
else
    python scripts/report_import_status.py --since-days "${LOOKBACK_DAYS}"
fi

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
echo ""
echo "Press Enter to close..."
[[ -t 0 ]] && read
exit 0
