# Transfer Ledger Handoff (Current Live Method)

Repo scope:
- canonical runtime path is this repo instance:
  - `~/Docs/Autonomous_business`

## Source of truth

- Operational truth: `db/app.db`
- Generated outputs only: `docs/transfer_ledger/*.md`

## Live control points

- Wrapper entrypoint:
  - `scripts/run_exchange_imports.sh`
- Autonomous pipeline:
  - `scripts/transfer_ledger_autopilot.py`
- Scheduler installer:
  - `scripts/install_exchange_scheduler.sh`
- LaunchAgent configs:
  - `config/com.example.exchange-import.plist`
  - `config/com.example.gmail-pubsub.plist`
  - `config/com.example.gmail-watch-refresh.plist`

## End-to-end flow (as running now)

1. Gmail real-time listener receives push notifications:
   - `com.example.gmail-pubsub` -> `scripts/gmail_pubsub_listener.sh`
2. Daily Gmail watch refresh keeps watch alive:
   - `com.example.gmail-watch-refresh` -> `scripts/gmail_watch_refresh.sh` at 02:15 local time
3. Every 6 hours, exchange wrapper runs:
   - `com.example.exchange-import` -> `scripts/run_exchange_imports.sh`
4. `run_exchange_imports.sh` executes:
   - IMAP fallback sweep for exchanger emails (`import_exchanger_emails.py`)
   - `transfer_ledger_autopilot.py --skip-emails --reports --report-days 0`
   - `sync_universal_usdt_balance.py` in apply mode only when `ENABLE_BANK_ACCOUNTS_WRITE=1`
   - apply mode also regenerates `config/bank_accounts_history_totals.md` from `config/bank_accounts_history.yaml`

## What autopilot imports

Inside `transfer_ledger_autopilot.py`, the pipeline covers:
- Binance P2P BUY orders (`binance_c2c_orders` + ledger legs)
- FX derivation and upsert (`dim_fx_rates`)
- Binance withdrawals (`binance_withdrawals` + withdrawal/fee ledger entries)
- Binance deposits
- Binance universal transfers
- Funding/account snapshots
- report generation (full history when `--report-days 0`)

## Important reports to monitor

- `docs/transfer_ledger/TRANSFER_LEDGER_FULL_HISTORY.md`
- `docs/transfer_ledger/P2P_BUY_FULL_HISTORY.md`
- `docs/transfer_ledger/EXCHANGER_BUY_FULL_HISTORY.md`
- `docs/transfer_ledger/PO_PAYMENTS_CHRONO_FULL_HISTORY.md`
- `docs/transfer_ledger/PO_PAYMENT_STATUS.md`
- `config/bank_accounts_history_totals.md` (bank history totals timeline, newest->oldest)

## Required env and controls

Required:
- Gmail: `GMAIL_USER`, `GMAIL_APP_PASSWORD`
- Binance: `BINANCE_TOKEN`, `BINANCE_SECRET_KEY`

Optional runtime controls:
- `EXCHANGE_LOOKBACK_DAYS` (default `30`)
- `EXCHANGE_EMAIL_LOOKBACK_DAYS` (default `7`)
- `ENABLE_BANK_ACCOUNTS_WRITE` (`1` to apply bank_accounts update; otherwise dry-run)

Optional report controls:
- `LEDGER_CURRENT_USDT`, `REPORT_CURRENT_USDT`, `CURRENT_USDT_BALANCE`
- `LEDGER_BALANCE_ROWS`

## Manual ops runbook

Full refresh now:
```bash
bash scripts/run_exchange_imports.sh
```

Strict ledger validation:
```bash
python3 scripts/validate_transfer_ledger.py --strict
```

Install/update schedulers:
```bash
bash scripts/install_exchange_scheduler.sh
launchctl list | grep exchange-import
```

## Guardrails

- No destructive git operations.
- Treat DB as truth; do not hand-edit generated markdown reports.
- For parallel agents, isolate DB writers by worktree/data-dir strategy to avoid race conditions.
