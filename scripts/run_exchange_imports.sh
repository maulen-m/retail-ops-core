#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_dotenv.sh"
load_dotenv "$ROOT_DIR/.env"

export EXCHANGE_LOOKBACK_DAYS="${EXCHANGE_LOOKBACK_DAYS:-30}"
export EXCHANGE_EMAIL_LOOKBACK_DAYS="${EXCHANGE_EMAIL_LOOKBACK_DAYS:-7}"

# Hybrid mode:
# 1) IMAP sweep as fallback in case Gmail push misses events
# 2) Binance + FX + reports via autonomous pipeline (email step skipped to avoid duplicate work)
python3 scripts/import_exchanger_emails.py --since-days "$EXCHANGE_EMAIL_LOOKBACK_DAYS"

python3 scripts/transfer_ledger_autopilot.py \
  --days "$EXCHANGE_LOOKBACK_DAYS" \
  --skip-emails \
  --reports \
  --report-days 0

if [[ "${ENABLE_BANK_ACCOUNTS_WRITE:-}" == "1" ]]; then
  python3 scripts/sync_universal_usdt_balance.py --apply
else
  python3 scripts/sync_universal_usdt_balance.py --dry-run
fi
