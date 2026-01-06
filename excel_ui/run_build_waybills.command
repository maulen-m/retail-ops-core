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
    set -a
    source .env
    set +a
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

echo "========================================"
echo "  Full Waybill Workflow"
echo "========================================"
echo ""
echo "Data root: ${DATA_ROOT}"
echo ""

# Preflight checks (CRM exists, backups, columns, shipping guard if enabled)
echo "Preflight: checking CRM + environment..."
echo "----------------------------------------"
if [ "${ENABLE_KASPI_WRITE}" = "1" ]; then
    SHIPPING_ENABLED=1
    python scripts/ops_preflight.py --shipping
else
    SHIPPING_ENABLED=0
    echo "WARNING: ENABLE_KASPI_WRITE is not set to 1. Shipping will be skipped."
    python scripts/ops_preflight.py
fi

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Preflight failed. Fix issues above and retry."
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""

# Sync DB from API + ActiveOrders (order lifecycle + line items)
echo "Sync: API -> DB (order lifecycle)..."
echo "----------------------------------------"
LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS:-4}"
SINCE_DATE=$(date -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)
python scripts/sync_kaspi_orders.py --all --since "$SINCE_DATE"
if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: API -> DB sync failed (see above)."
    echo "Continuing to next step..."
fi

echo ""
echo "Sync: ActiveOrders -> DB (line items)..."
echo "----------------------------------------"
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    echo "Preflight: checking ActiveOrders columns..."
    python scripts/validate_activeorders_columns.py excel_ui/ActiveOrders/ActiveOrders.xlsx
    if [ $? -ne 0 ]; then
        echo ""
        echo "WARNING: ActiveOrders columns mismatch (see above)."
        echo "Continuing to ingest anyway..."
    fi
    echo ""
    python scripts/ingest_kaspi_export.py excel_ui/ActiveOrders/ActiveOrders.xlsx
    if [ $? -ne 0 ]; then
        echo ""
        echo "WARNING: ActiveOrders -> DB ingest failed (see above)."
        echo "Continuing to next step..."
    fi
else
    echo "WARNING: ActiveOrders.xlsx not found; skipping ActiveOrders -> DB ingest."
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
python scripts/validate_pending_orders.py
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
    python scripts/ship_orders_api.py --verbose --since-days "${LOOKBACK_DAYS}"

    if [ $? -ne 0 ]; then
        echo ""
        echo "WARNING: Ship orders encountered errors (see above)"
        echo "Continuing to next step..."
    fi

    echo ""
else
    echo "Step 1: Shipping orders skipped (ENABLE_KASPI_WRITE != 1)"
    echo ""
fi

# Step 2: Download waybills
echo "Step 2: Downloading waybills via API..."
echo "----------------------------------------"
python scripts/download_waybills_api.py --verbose --days "${LOOKBACK_DAYS}" --exact-date --fallback-crm

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Download waybills encountered errors (see above)"
    echo "Continuing to next step..."
fi

echo ""

# Step 3: Build waybill bundles
echo "Step 3: Building waybill bundles..."
echo "----------------------------------------"
python scripts/build_daily_waybills.py --verbose --lookback-days "${LOOKBACK_DAYS}" --exact-date

echo ""
# Archive inputs (CRM + waybill PDFs) for backup
echo "Archiving inputs (CRM + waybill PDFs)..."
echo "----------------------------------------"
TS=$(date "+%Y-%m-%d_%H%M%S")
ARCHIVE_DIR="${DATA_ROOT}/excel_ui/Archive/input_${TS}"
EXTERNAL_BACKUP_ROOT="~/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business"
EXTERNAL_ARCHIVE_DIR="${EXTERNAL_BACKUP_ROOT}/Kaspi_waybills/input_${TS}"
EXTERNAL_PDFS_DIR="${EXTERNAL_BACKUP_ROOT}/Kaspi_waybills/pdfs_${TS}"
mkdir -p "${ARCHIVE_DIR}/waybills"
mkdir -p "${EXTERNAL_ARCHIVE_DIR}/waybills"
mkdir -p "${EXTERNAL_PDFS_DIR}"
cp -p "${DATA_ROOT}/excel_ui/SALES_KSP_CRM_V3.xlsx" "${ARCHIVE_DIR}/" 2>/dev/null || true
cp -p "${DATA_ROOT}/excel_ui/SALES_KSP_CRM_V3.xlsx" "${EXTERNAL_ARCHIVE_DIR}/" 2>/dev/null || true
if [ -d "${DATA_ROOT}/excel_ui/ActiveOrders/waybills" ]; then
    cp -p "${DATA_ROOT}/excel_ui/ActiveOrders/waybills/"*.pdf "${ARCHIVE_DIR}/waybills/" 2>/dev/null || true
    cp -p "${DATA_ROOT}/excel_ui/ActiveOrders/waybills/"*.pdf "${EXTERNAL_ARCHIVE_DIR}/waybills/" 2>/dev/null || true
fi
if [ -d "${DATA_ROOT}/excel_ui/ActiveOrders" ]; then
    cp -p "${DATA_ROOT}/excel_ui/ActiveOrders/"waybill*.zip "${ARCHIVE_DIR}/" 2>/dev/null || true
    cp -p "${DATA_ROOT}/excel_ui/ActiveOrders/"waybill*.zip "${EXTERNAL_ARCHIVE_DIR}/" 2>/dev/null || true
fi
if [ -d "${DATA_ROOT}/excel_ui/Kaspi_orders/Today" ]; then
    cp -p "${DATA_ROOT}/excel_ui/Kaspi_orders/Today/"*.pdf "${EXTERNAL_PDFS_DIR}/" 2>/dev/null || true
    cp -p "${DATA_ROOT}/excel_ui/Kaspi_orders/Today/"*/*.pdf "${EXTERNAL_PDFS_DIR}/" 2>/dev/null || true
    cp -p "${DATA_ROOT}/excel_ui/Kaspi_orders/Today/"*/*/*.pdf "${EXTERNAL_PDFS_DIR}/" 2>/dev/null || true
fi
echo "Archived inputs to: ${ARCHIVE_DIR}"
echo "Archived inputs to: ${EXTERNAL_ARCHIVE_DIR}"
echo "Archived output PDFs to: ${EXTERNAL_PDFS_DIR}"

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
echo "Output folder (resolved): ${DATA_ROOT}/excel_ui/Kaspi_orders/Today/"

echo ""
echo "Final Report: waybill health"
echo "----------------------------------------"
python scripts/report_waybill_status.py --since-days "${LOOKBACK_DAYS}"
echo ""
echo "Press Enter to close..."
read
