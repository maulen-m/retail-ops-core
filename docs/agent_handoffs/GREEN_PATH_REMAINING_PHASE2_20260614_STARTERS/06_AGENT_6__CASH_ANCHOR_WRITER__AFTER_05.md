# Agent 6 - Cash Anchor Writer

## Selected Lane For Launch 2026-06-14 08:23 +05

The orchestrator selects **PKT-CASH / G-CASH-01 only** for this launch.

Current boundary:
- Current production DB SHA before launch: `5d2233bf8a0956d95a1cac39b416553b81a6db8ee9879d5e364b1d61ca0307d9`.
- Agent 3 returned RED because a read-only cash validator refreshed SQLite views and changed DB SHA. Integrity, cashflow invariants, and DB guard passed afterward. Treat the current SHA as the accepted boundary.
- `G-FX-01` is GREEN. `G-FX-02` is PARTIAL. Cash anchor may proceed on OD-002 owner snapshot; do not wait for COGS.

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent3_cash_anchor_scout_closeout.md`
7. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
8. `~/Docs/Autonomous_business/docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`
9. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/06_AGENT_6__CASH_ANCHOR_WRITER__AFTER_05.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent6_cash_anchor_writer_closeout.md`

Role:
Single write-capable execution agent for G-CASH-01 only.

Objective:
Create and apply a governed OD-002 workbook-snapshot cash anchor route only if it can produce the required `cashflow_cash_anchor` evidence, preserve all source provenance, and pass cash validators. If the repo cannot support a safe governed anchor writer in this lane, stop with `Gate: RED` or `Gate: YELLOW`; do not fake an anchor with ad hoc SQL.

Owner-approved source:
- Workbook: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
- Sheet: `Cash_Balances`
- Snapshot column/header: `13.06.2026_01_01_26`
- Operating cash excluding reserve: `3937364` KZT-eq.
- Reserve: `1500000` KZT, record separately as reserve/non-operating context unless an existing contract says it belongs in operating close.
- Grand total with reserve: `5437364` KZT-eq, record as metadata/context, not silently as operating cash.
- FX basis: USD/USDT at `485`, RUB at `6`, CNY working ref at `72`.
- In-flight context: SHR true remaining `44101 CNY`; PO-1B remaining about `17621 CNY` via Binance starting 2026-06-13. Record as explanation/commitment context; do not create actual bank/Binance movements.

Allowed:
- Add or patch a narrow governed script for OD-002 workbook snapshot -> `cashflow_cash_anchor` batch and any necessary cashflow adjustment/rebuild path.
- Add focused tests for parser, dry-run, env gate, exact anchor rows, reserve handling, rollback metadata, and no accidental partial-range reset.
- Production DB apply is allowed only after:
  - `sqlite3 .backup` backup exists and passes `PRAGMA integrity_check`;
  - dry-run on scratch/copy proves exact intended rows;
  - explicit env gate is required and used;
  - pre/post DB SHA recorded;
  - the output evidence root records source workbook path, snapshot header, account/currency coverage, reserve treatment, FX basis, and rollback commands.
- Use copied DBs for validator probes that might refresh views. Do not run known DB-mutating validators on production unless they are fixed first.

Forbidden:
- No external banking, Binance, Telegram, LaunchAgent, Kaspi, Repricer, browser, workbook, or customer/operator-message actions.
- No COGS override, stock, returns, quarantine, pricing, PO, or ads writes.
- No manual SQL inserts outside a governed script.
- No silent choice between operating cash and reserve-inclusive cash.
- No partial-range rebuild that resets opening balances.
- No dashboard/scoreboard/status edits; the orchestrator owns those.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Exact files changed.
- DB backup path, backup integrity result, pre/post DB SHA, and rollback command if DB touched.
- Dry-run evidence and apply evidence.
- Before/after `cashflow_cash_anchor` rows for `2026-06-13`.
- Before/after `fact_cashflow_daily` close for `2026-06-13`.
- Cash validators run and key outputs.
- Current DB SHA before/after proving only intended DB mutation occurred.
