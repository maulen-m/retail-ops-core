#!/bin/bash
# V2 Waybill workflow - optimized (reads CRM only once)
#
# Differences from V1:
# - Downloads waybills directly from API filtered by planned date
# - NO CRM read before download (saves 30-60 seconds)
# - CRM is only read once during build step
#
# Steps:
# 1. Ship orders (set package count via API) - still reads CRM
# 2. Download waybills V2 (API-direct, no CRM read)
# 3. Build waybill bundles (reads CRM once)

cd ~/Docs/Autonomous_business
source .venv/bin/activate

echo "========================================"
echo "  Waybill Workflow V2 (Optimized)"
echo "========================================"
echo ""

# Step 1: Ship orders (set package count)
echo "Step 1: Shipping orders..."
python scripts/ship_orders_api.py --verbose
echo ""

# Step 2: Download waybills V2 (no CRM read)
echo "Step 2: Downloading waybills (V2 - API direct)..."
python scripts/download_waybills_v2.py --verbose
echo ""

# Step 3: Build waybill bundles
echo "Step 3: Building waybill bundles..."
python scripts/build_daily_waybills.py --verbose
echo ""

echo "========================================"
echo "  Workflow Complete"
echo "========================================"
