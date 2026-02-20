#!/bin/bash
# Wrapper: run full import with 14-day lookback

cd ~/Docs/Autonomous_business
export KASPI_LOOKBACK_DAYS=14
exec /bin/bash excel_ui/run_full_import.command
