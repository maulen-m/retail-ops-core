# Transfer Ledger

Scope: track KZT -> USDT -> CNY supplier funding and PO payment progress in one auditable flow.

Principles:
- DB is truth (`db/app.db`).
- Reports are generated views (`docs/transfer_ledger/*.md`).
- Ledger entries are immutable (corrections are new rows).
- FX must be explicit per entry.

See `docs/transfer_ledger/CONTRACTS.md` for invariants.

## Live Runtime Method (current production path)

Primary entrypoint:
- `scripts/run_exchange_imports.sh`

What it does end-to-end:
1. Loads `.env` safely through `scripts/load_dotenv.sh`.
2. Runs IMAP fallback sweep:
   - `python3 scripts/import_exchanger_emails.py --since-days "$EXCHANGE_EMAIL_LOOKBACK_DAYS"`
3. Runs autonomous Binance/FX/report pipeline:
   - `python3 scripts/transfer_ledger_autopilot.py --days "$EXCHANGE_LOOKBACK_DAYS" --skip-emails --reports --report-days 0`
4. Syncs `UNIVERSAL/binance_usdt` into bank config:
   - apply mode only if `ENABLE_BANK_ACCOUNTS_WRITE=1`
   - otherwise dry-run

Defaults used by wrapper:
- `EXCHANGE_LOOKBACK_DAYS=30`
- `EXCHANGE_EMAIL_LOOKBACK_DAYS=7`

## Scheduler Topology (launchd)

Install/update schedulers:
- `scripts/install_exchange_scheduler.sh`

Installed jobs:
- `com.example.gmail-pubsub`
  - command: `scripts/gmail_pubsub_listener.sh`
  - mode: keepalive listener
- `com.example.gmail-watch-refresh`
  - command: `scripts/gmail_watch_refresh.sh`
  - schedule: daily `02:15` local macOS time
- `com.example.exchange-import`
  - command: `scripts/run_exchange_imports.sh`
  - schedule: every `21600` seconds (6 hours)

## Inputs

Required env:
- Gmail IMAP: `GMAIL_USER`, `GMAIL_APP_PASSWORD`
- Binance API: `BINANCE_TOKEN`, `BINANCE_SECRET_KEY`

Optional env:
- Gmail filters/labels: `GMAIL_MAILBOX*`, `GMAIL_QUERY*`
- Report/balance overrides: `LEDGER_CURRENT_USDT`, `REPORT_CURRENT_USDT`, `CURRENT_USDT_BALANCE`, `LEDGER_BALANCE_ROWS`
- Runtime control: `EXCHANGE_LOOKBACK_DAYS`, `EXCHANGE_EMAIL_LOOKBACK_DAYS`, `ENABLE_BANK_ACCOUNTS_WRITE`

## Outputs

Main generated reports:
- `docs/transfer_ledger/TRANSFER_LEDGER_FULL_HISTORY.md`
- `docs/transfer_ledger/P2P_BUY_FULL_HISTORY.md`
- `docs/transfer_ledger/EXCHANGER_BUY_FULL_HISTORY.md`
- `docs/transfer_ledger/PO_PAYMENTS_CHRONO_FULL_HISTORY.md`
- `docs/transfer_ledger/PO_PAYMENT_STATUS.md`

## Validation

Transfer-ledger correctness gate:
- `python3 scripts/validate_transfer_ledger.py --strict`

PO allocation (many-to-many) stays available via:
- `python3 scripts/transfer_ledger_cli.py allocate-po ...`
