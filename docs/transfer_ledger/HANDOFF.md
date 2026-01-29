# Transfer Ledger Handoff (Worktree: ledger)

Purpose
- This worktree isolates transfer-ledger changes from other agents.
- It lives inside the same repo as ~/Docs/Autonomous_business, but on its own branch.

Worktree + Branch
- Worktree path: ~/.claude-worktrees/Autonomous_business/ledger
- Branch: ledger (tracks origin/ledger)

Source of Truth
- Database: db/app.db (all ledger, PO allocation, FX data)
- Reports: docs/transfer_ledger/*.md (generated outputs only)

Key Flows (data in)
1) Binance P2P (KZT -> USDT)
   - scripts/import_binance_p2p.py
2) Binance withdrawals (USDT -> TRC20)
   - scripts/import_binance_withdrawals.py
3) Exchanger emails (USDT -> CNY)
   - scripts/import_exchanger_emails.py
4) Gmail push/IMAP sync
   - scripts/gmail_sync_history.py (email labels)
5) Autopilot (runs the full chain + reports)
   - scripts/transfer_ledger_autopilot.py

Notifications
- Telegram bot for exchanger updates + /Pay_PO summary
  - scripts/telegram_ledger_bot.py
  - core/transfer_ledger/telegram_ledger_alerts.py

Important Reports
- docs/transfer_ledger/TRANSFER_LEDGER_FULL_HISTORY.md
- docs/transfer_ledger/P2P_BUY_FULL_HISTORY.md
- docs/transfer_ledger/EXCHANGER_BUY_FULL_HISTORY.md
- docs/transfer_ledger/PO_PAYMENTS_CHRONO_FULL_HISTORY.md
- docs/transfer_ledger/PO_PAYMENT_STATUS.md

Env Controls (examples)
- Ledger balance override used in reports:
  - LEDGER_CURRENT_USDT=690.330471
  - REPORT_CURRENT_USDT=690.330471
  - CURRENT_USDT_BALANCE=690.330471
- Appendix length:
  - LEDGER_BALANCE_ROWS=80
- Telegram:
  - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ALLOWED_CHAT_IDS (optional)
- Gmail:
  - GMAIL_USER, GMAIL_APP_PASSWORD, mailbox/query vars
- Binance:
  - BINANCE_TOKEN, BINANCE_SECRET_KEY

Runbook (typical refresh)
1) Pull emails + match withdrawals:
   - python3 scripts/gmail_sync_history.py
2) Import P2P and withdrawals:
   - python3 scripts/import_binance_p2p.py --days 120 --trade-type BUY
   - python3 scripts/import_binance_withdrawals.py --days 120 --coin USDT
3) Derive FX + reports:
   - python3 scripts/derive_fx_rates.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
   - python3 scripts/generate_transfer_ledger_reports.py

Cherry-pick to main repo
- From main repo:
  - git fetch origin
  - git log --oneline origin/ledger
  - git cherry-pick <commit1> <commit2> ...

Guardrails
- No destructive git ops (no reset --hard, no force push).
- Avoid concurrent DB writes from multiple worktrees.
- Keep .claude/*.md edits in a single "scribe" worktree to prevent conflicts.
