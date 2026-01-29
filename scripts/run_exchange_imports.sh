#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export EXCHANGE_LOOKBACK_DAYS="${EXCHANGE_LOOKBACK_DAYS:-7}"
export EXCHANGE_EMAIL_LOOKBACK_DAYS="${EXCHANGE_EMAIL_LOOKBACK_DAYS:-3}"

python3 scripts/import_binance_p2p.py --trade-type BUY --days "$EXCHANGE_LOOKBACK_DAYS"
python3 scripts/import_binance_withdrawals.py --coin USDT --days "$EXCHANGE_LOOKBACK_DAYS"
python3 scripts/import_exchanger_emails.py --since-days "$EXCHANGE_EMAIL_LOOKBACK_DAYS"
