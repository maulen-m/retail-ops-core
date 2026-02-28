#!/bin/bash
# Full automated waybill workflow:
# 1. Ship orders (set package count via API)
# 2. Download waybills (via API)
# 3. Build waybill bundles
#
# Phase 12: Automated Kaspi shipping workflow
#
# Prerequisites:
#   1. Run import script first (run_import_orders.command)
#   2. Fill MY_SIZE column in SALES_KSP_CRM_V3.xlsx
#   3. Set ENABLE_KASPI_WRITE=1 in .env for shipping

cd ~/Docs/Autonomous_business
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

# Ensure PDF merge dependency is available (pypdf preferred)
python - <<'PY'
try:
    import pypdf  # noqa: F401
except Exception:
    try:
        import PyPDF2  # noqa: F401
    except Exception:
        raise SystemExit(1)
raise SystemExit(0)
PY
if [ $? -ne 0 ]; then
    echo "Missing PDF merge dependency (pypdf/PyPDF2). Installing pypdf..."
    python -m pip install --quiet pypdf
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install pypdf. Please run: python3 -m pip install pypdf"
        echo "Press Enter to close..."
        read
        exit 1
    fi
fi

if [ -z "${AB_DATA_DIR:-}" ] && [ -z "${DATA_DIR:-}" ]; then
    export DATA_DIR="~/Docs/Autonomous_business"
fi
DATA_ROOT="${AB_DATA_DIR:-${DATA_DIR:-~/Docs/Autonomous_business}}"
OUTPUT_TODAY_DIR="${DATA_ROOT}/excel_ui/Kaspi_orders/Today"

# Merchant UID headers (store-specific). Prefer config/kaspi_stores.yaml when available.
MERCHANT_EXPORTS=$(python3 - <<'PY' 2>/dev/null
from pathlib import Path
import sys
try:
    import yaml
except Exception:
    sys.exit(0)

config_path = Path("config/kaspi_stores.yaml")
if not config_path.exists():
    sys.exit(0)

config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
stores = config.get("stores") or {}
for store_code, info in stores.items():
    if not isinstance(info, dict):
        continue
    uid = info.get("merchant_uid") or info.get("account_id")
    if uid:
        print(f'export KASPI_MERCHANT_UID_{store_code.upper()}=\"{uid}\"')
PY
)
if [ -n "${MERCHANT_EXPORTS}" ]; then
    eval "${MERCHANT_EXPORTS}"
fi

# Fallback defaults (if config/env missing)
export KASPI_MERCHANT_UID_UNIVERSAL="${KASPI_MERCHANT_UID_UNIVERSAL:-30000001}"
export KASPI_MERCHANT_UID_ACMEWEAR="${KASPI_MERCHANT_UID_ACMEWEAR:-30137883}"
export KASPI_MERCHANT_UID_11KZ="${KASPI_MERCHANT_UID_11KZ:-30290083}"
export KASPI_MERCHANT_UID_MELVIS="${KASPI_MERCHANT_UID_MELVIS:-30362323}"
export KASPI_MERCHANT_UID_STOREB="${KASPI_MERCHANT_UID_STOREB:-30000002}"

echo "========================================"
echo "  Full Waybill Workflow (Per-Store + MERGED)"
echo "========================================"
echo ""
echo "Data root: ${DATA_ROOT}"
echo ""

# Preflight checks (CRM exists, backups, columns, shipping guard if enabled)
echo "Preflight: checking CRM + environment..."
echo "----------------------------------------"
if [ -z "${ENABLE_KASPI_WRITE:-}" ]; then
    echo "ERROR: ENABLE_KASPI_WRITE is not set. Did .env load?"
    echo "Press Enter to close..."
    read
    exit 1
fi
if [ "${ENABLE_KASPI_WRITE}" != "1" ]; then
    echo "ERROR: ENABLE_KASPI_WRITE=${ENABLE_KASPI_WRITE} (set to 1 in .env to ship)"
    echo "Press Enter to close..."
    read
    exit 1
fi
SHIPPING_ENABLED=1
python scripts/ops_preflight.py --shipping

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Preflight failed. Fix issues above and retry."
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""
echo "Preflight: shipment hard gates..."
echo "----------------------------------------"
python scripts/preflight_shipment.py --project-root "${DATA_ROOT}"

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Shipment hard preflight failed. Fix issues above and retry."
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""

# Track hard gate failures and exit non-zero at end.
HARD_FAIL=0

# Sync DB from API + ActiveOrders (order lifecycle + line items)
echo "Sync: API -> DB (order lifecycle)..."
echo "----------------------------------------"
LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS:-3}"
SINCE_DATE=$(date -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)
python scripts/sync_kaspi_orders.py --all --since "$SINCE_DATE"
if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: API -> DB sync failed (see above)."
    echo "Continuing to next step..."
fi

echo ""

# Sync CRM manual sizes into DB (safe to re-run)
echo "Sync: CRM manual sizes -> DB..."
echo "----------------------------------------"
python scripts/sync_crm_sizes_to_db.py --upsert-missing

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: CRM size sync failed (see above)."
    echo "Continuing to shipping step..."
fi

echo ""

# Validate pending orders alignment (CRM vs DB/ActiveOrders)
echo "Preflight: validating pending orders..."
echo "----------------------------------------"
INCLUDE_OVERDUE="${KASPI_INCLUDE_OVERDUE:-1}"
PENDING_ARGS=""
if [ "${INCLUDE_OVERDUE}" = "1" ]; then
    PENDING_ARGS="--include-overdue --lookback-days ${LOOKBACK_DAYS}"
fi
python scripts/validate_pending_orders.py ${PENDING_ARGS}
if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Pending order validation reported mismatches (see above)."
    echo "Continuing to shipping step..."
fi

echo ""

# Step 1: Ship orders (set package count) if enabled
if [ "${SHIPPING_ENABLED}" -eq 1 ]; then
    echo "Step 1: Shipping orders (setting package count)..."
    echo "----------------------------------------"
    SHIP_STORES="${KASPI_SHIP_STORES:-Universal AcmeWear 11KZ Store-C STORE-B}"
    if [ "${SHIP_STORES}" = "ALL" ]; then
        SHIP_STORES="Universal AcmeWear 11KZ Store-C STORE-B"
    fi
    ASSEMBLE_DIR="${DATA_ROOT}/excel_ui/assemble_per_store"
    for STORE in ${SHIP_STORES}; do
        STORE_LABEL=""
        SCRIPT_PATH=""
        case "${STORE}" in
            Universal|UNIVERSAL)
                STORE_LABEL="Universal"
                SCRIPT_PATH="${ASSEMBLE_DIR}/run_assemble_universal.command"
                ;;
            AcmeWear|ACMEWEAR)
                STORE_LABEL="AcmeWear"
                SCRIPT_PATH="${ASSEMBLE_DIR}/run_assemble_acmewear.command"
                ;;
            11KZ|store-d|11kZ)
                STORE_LABEL="11KZ"
                SCRIPT_PATH="${ASSEMBLE_DIR}/run_assemble_store-d.command"
                ;;
            Store-C|MELVIS)
                STORE_LABEL="Store-C"
                SCRIPT_PATH="${ASSEMBLE_DIR}/run_assemble_store-c.command"
                ;;
            STORE-B|STOREB|Mgroup)
                STORE_LABEL="STORE-B"
                SCRIPT_PATH="${ASSEMBLE_DIR}/run_assemble_storeb.command"
                ;;
            *)
                echo "WARNING: Unknown store in KASPI_SHIP_STORES: ${STORE}. Skipping."
                continue
                ;;
        esac
        echo ""
        echo "Shipping store: ${STORE_LABEL}"
        if [ -x "${SCRIPT_PATH}" ]; then
            SKIP_PREFLIGHT=1 SKIP_WAIT=1 "${SCRIPT_PATH}"
        else
            python scripts/ship_orders_api.py --verbose --since-days "${LOOKBACK_DAYS}" --store "${STORE_LABEL}"
        fi
        if [ $? -ne 0 ]; then
            echo ""
            echo "WARNING: Ship orders encountered errors for ${STORE_LABEL} (see above)"
            HARD_FAIL=1
            echo "Continuing to next store..."
        fi
    done

    echo ""
else
    echo "Step 1: Shipping orders skipped (ENABLE_KASPI_WRITE != 1)"
    echo ""
fi

# Step 2: Download waybills
echo "Step 2: Downloading waybills via API..."
echo "----------------------------------------"
DATE_FLAG="--exact-date"
if [ "${INCLUDE_OVERDUE}" = "1" ]; then
    DATE_FLAG="--include-overdue"
fi
ALLOW_PARTIAL_WAYBILL_HEALTH="${KASPI_ALLOW_PARTIAL_WAYBILL_HEALTH:-1}"
PARTIAL_HEALTH_FLAG=""
if [ "${ALLOW_PARTIAL_WAYBILL_HEALTH}" = "1" ]; then
    PARTIAL_HEALTH_FLAG="--allow-partial-health"
fi
python scripts/download_waybills_api.py --verbose --days "${LOOKBACK_DAYS}" ${DATE_FLAG} --fallback-crm ${PARTIAL_HEALTH_FLAG}

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Download waybills encountered errors (see above)"
    HARD_FAIL=1
    echo "Continuing to next step..."
fi

echo ""

# Step 3: Build waybill bundles
echo "Step 3: Building waybill bundles (PER_STORE + MERGED)..."
echo "----------------------------------------"
if [ "${HARD_FAIL}" -ne 0 ]; then
    echo "SKIPPED: build step blocked by earlier hard failure."
    if [ -d "${OUTPUT_TODAY_DIR}" ]; then
        rm -rf "${OUTPUT_TODAY_DIR}"
    fi
    mkdir -p "${OUTPUT_TODAY_DIR}"
    echo "Cleared stale output folder: ${OUTPUT_TODAY_DIR}"
else
    python scripts/build_daily_waybills.py --verbose --lookback-days "${LOOKBACK_DAYS}" ${DATE_FLAG} --output-layout per-store-and-merged
    if [ $? -ne 0 ]; then
        echo ""
        echo "WARNING: Build waybill bundles encountered errors (see above)"
        HARD_FAIL=1
    fi
fi

echo ""
# Archive inputs (CRM + waybill PDFs) for backup
echo "Archiving inputs (CRM + waybill PDFs)..."
echo "----------------------------------------"
EXTERNAL_BACKUP_ROOT="~/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business"
EXTERNAL_GDRIVE_KASPI_ROOT="${EXTERNAL_BACKUP_ROOT}/Kaspi_waybills"
EXTERNAL_DB_ROOT="${KASPI_EXTERNAL_DB_ROOT:-~/Documents/useful tables/Main crm spreadsheets/main tables/External_database}"
EXTERNAL_DB_REPO_LABEL="${KASPI_EXTERNAL_DB_REPO_LABEL:-Autonomous_business}"
CACHE_RETENTION_DAYS="${KASPI_WAYBILL_CACHE_RETENTION_DAYS:-30}"
ARCHIVE_RETENTION_DAYS="${KASPI_ARCHIVE_RETENTION_DAYS:-14}"

python scripts/archive_waybill_inputs.py \
    --data-root "${DATA_ROOT}" \
    --selection-cache "${DATA_ROOT}/excel_ui/ActiveOrders/waybills/_waybill_selection_orders.json" \
    --crm-file "${DATA_ROOT}/excel_ui/SALES_KSP_CRM_V3.xlsx" \
    --waybill-dir "${DATA_ROOT}/excel_ui/ActiveOrders/waybills" \
    --active-orders-dir "${DATA_ROOT}/excel_ui/ActiveOrders" \
    --archive-root "${DATA_ROOT}/excel_ui/Archive" \
    --gdrive-archive-root "${EXTERNAL_GDRIVE_KASPI_ROOT}" \
    --external-db-root "${EXTERNAL_DB_ROOT}" \
    --repo-label "${EXTERNAL_DB_REPO_LABEL}" \
    --cache-retention-days "${CACHE_RETENTION_DAYS}" \
    --archive-retention-days "${ARCHIVE_RETENTION_DAYS}" \
    --verbose
if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Input archiving encountered errors (see above)."
    echo "Continuing workflow..."
fi

echo ""
STATUS_FILE="${DATA_ROOT}/excel_ui/ActiveOrders/waybills/_waybill_selection_status.txt"
if [ -f "${STATUS_FILE}" ]; then
    SELECTION_STATUS=$(grep -E "^selection=" "${STATUS_FILE}" | head -n 1 | cut -d= -f2-)
    FALLBACK_STORES=$(grep -E "^fallback_stores=" "${STATUS_FILE}" | head -n 1 | cut -d= -f2-)
    API_ERRORS=$(grep -E "^api_errors=" "${STATUS_FILE}" | head -n 1 | cut -d= -f2-)
    if [ -n "${SELECTION_STATUS}" ]; then
        if [ -n "${FALLBACK_STORES}" ]; then
            echo "Selection status: ${SELECTION_STATUS} (stores: ${FALLBACK_STORES})"
        elif [ -n "${API_ERRORS}" ]; then
            echo "Selection status: ${SELECTION_STATUS} (stores: ${API_ERRORS})"
        else
            echo "Selection status: ${SELECTION_STATUS}"
        fi
        echo ""
    fi
fi

echo "========================================"
echo "  Workflow Complete!"
echo "========================================"
echo "Output folder: excel_ui/Kaspi_orders/Today/"
echo "Output folder (resolved): ${OUTPUT_TODAY_DIR}/"
echo "Per-store bundles: ${OUTPUT_TODAY_DIR}/PER_STORE/"
echo "Merged bundles: ${OUTPUT_TODAY_DIR}/MERGED/"

echo ""
echo "Final Report: waybill health"
echo "----------------------------------------"
if [ "${INCLUDE_OVERDUE}" = "1" ]; then
    python scripts/report_waybill_status.py --since-days "${LOOKBACK_DAYS}" --include-overdue --strict-stopline
else
    python scripts/report_waybill_status.py --since-days "${LOOKBACK_DAYS}" --strict-stopline
fi
if [ $? -ne 0 ]; then
    HARD_FAIL=1
fi

if [ "${HARD_FAIL}" -ne 0 ]; then
    echo ""
    echo "STOP-LINE: workflow completed with hard failures. See warnings above."
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""
echo "Press Enter to close..."
read
