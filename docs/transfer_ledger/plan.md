# Transfer Ledger Improvements — Plan (v1.1)

Owner: Adil / Code Captain  
Status: Proposed (ready to execute)  
Last updated: 2026-01-14

## 0) Goal (business outcome)

Make supplier-payment ops (KZT→USDT→CNY→Supplier/PO) **fast, auditable, low-error**:

- Near-zero manual reconciliation work
- Matching + allocation are deterministic (no “silent wrong”)
- Telegram becomes the **primary ops UI** for anomalies + approvals
- Reports remain generated artifacts; DB remains the truth

Success metric:
- Routine supplier funding + PO payment tracking takes **<10 minutes/day** unless there are real anomalies.


## 1) Current State (as-is)

- Source of truth is SQLite DB `db/app.db`; markdown reports in `docs/transfer_ledger/*.md` are generated outputs only.
- Report generator supports a manual “current USDT balance” override via env vars and a configurable reconciliation appendix row-count.
- Withdrawal fee is treated as part of the effective USDT outflow (fee-inclusive logic).
- Telegram alert helper exists for exchanger updates (message includes a PO summary), but Telegram is not yet a full ops UI.


## 2) Problems / Inefficiencies (why we’re changing)

### A) Correctness / capital-risk issues
1) **Unaudited manual balance override**
   - Env var overrides are powerful but risky: no “who/when/why”, easy to leave enabled accidentally.

2) **Hidden failure modes**
   - Any `except: pass` / “quiet fallback” around DB schema or reads can hide broken ingestion or missing tables.

3) **Matching safety**
   - Withdrawal↔exchanger matching must guarantee:
     - one withdrawal cannot be “reused” across multiple exchanger orders unless explicitly split
     - address matching is consistent (full/partial normalization)
     - amount tolerance policy is explicit and tested
     - time-window logic is explicit and tested

4) **Freshness/completeness ambiguity**
   - Reports show “sources last updated”, but if a source is blank or not implemented, operators don’t know whether it’s “missing data” or “not applicable”.

5) **Float math**
   - Currency math should be DECIMAL/quantized to avoid tiny negative leftovers and confusing “overpaid by -0.05” artifacts.


### B) Workflow inefficiency
1) Too many manual steps to answer basic operational questions:
   - “What’s free USDT?”
   - “Which PO is still unpaid?”
   - “Which exchanger order is unmatched?”
   - “Do we have a balance drift vs Binance?”

2) Allocation ambiguity costs time:
   - “Auto allocation by PO date rules” is fine as a default, but edge cases (missing PO dates, delayed emails, partial payments) need a fast resolution UI.

3) Telegram is currently alerts-only; it should be “chatops” UI:
   - alert → approve/fix → DB update → report refreshed


### C) Engineering inefficiency
1) Matching logic risks duplication across:
   - report generator
   - telegram alert builder
   - any future bots/scripts

2) Missing “ledger correctness gate”:
   - We should treat ledger correctness like PO/dashboard correctness: a deterministic contract gate.


## 3) Design Rules (non-negotiables)

- DB is truth; reports are views; Telegram is UI.
- Every write is idempotent and audited (who/when/source/note).
- No silent fallbacks: missing table/data surfaces loudly (report + Telegram + strict gate).
- Protect capital: never mark a PO “paid” unless reconciliation/matching is valid within explicit tolerances.


## 4) Work Plan (ordered by ROI / risk)

### Milestone M1 — Correctness Gate + Remove Ambiguity (NOW)
**Goal:** eliminate silent errors and lock correctness.

Tasks:
1) Create `scripts/validate_transfer_ledger.py` (strict + non-strict modes)
   - Validates:
     - matching invariants
     - allocation invariants
     - reconciliation invariants
     - freshness/completeness invariants (explicit)

2) Add deterministic contract tests:
   - `tests/test_transfer_ledger_contract.py`
   - Include fixtures that simulate:
     - exact match
     - partial address match (prefix+suffix)
     - fee-inclusive amount match
     - unmatched withdrawal older than threshold
     - split-required scenario

3) Centralize matching into one module:
   - Add/extend: `core/transfer_ledger/matching.py`
   - Export a single “official” matcher used everywhere:
     - report generator
     - telegram alert builder
     - any future bot/CLI

4) Remove any silent exception patterns:
   - Replace `except: pass` with:
     - explicit “table missing” handling and operator-visible messaging
     - strict mode raising errors

5) Add DECIMAL policy:
   - Central `money.py` helper (or similar):
     - Decimal quantization rules per currency (USDT 0.01, CNY 0.01, KZT 1.0)
     - explicit epsilon/tolerance constants

Acceptance criteria (M1):
- `pytest -q tests/test_transfer_ledger_contract.py` passes.
- safe_ship includes the new ledger gate.
- No silent fallbacks remain in ledger validation/reporting paths.


### Milestone M2 — Make “Current USDT” Audited + Reconciled (NEXT)
**Goal:** stop relying on env vars for normal ops.

Tasks:
1) Add table `ledger_balance_snapshots`:
   - snapshot_at (tz-aware datetime)
   - source: API / MANUAL / OTHER
   - usdt_balance (DECIMAL)
   - note
   - created_at, created_by

2) Change report “current USDT” selection policy:
   - use latest API snapshot (<=24h)
   - if a MANUAL snapshot is newer, use it
   - env override remains emergency-only and prints a loud banner in report output

3) Add Telegram admin command:
   - `/balance_set <USDT> [note]` → writes MANUAL snapshot
   - Inline confirm required

Acceptance criteria (M2):
- Normal operations never need env overrides.
- Reports always show which balance source was used (API vs MANUAL vs ENV emergency).


### Milestone M3 — Telegram as the Ops UI (HIGH ROI)
**Goal:** reduce human time + error by turning Telegram into the “control plane.”

#### 3.1 Bot behavior principles
- Low-noise (actionable alerts only)
- One-tap resolution (inline buttons)
- Writes require confirmation
- Every write creates an audit record

#### 3.2 Core commands (read-only)
- `/balance`
  - current funding USDT (API), ledger computed USDT, diff, last 10 recon rows
- `/unmatched`
  - withdrawals without exchanger email (with age)
  - exchanger orders without withdrawals (with age)
- `/po <PO_ID>`
  - total/paid/left in CNY + implied USDT rates + last 5 payments
- `/pos_due`
  - list POs with left>0 sorted by PO date (or due heuristic)
- `/fx`
  - last 7-day USDT/KZT and USDT/CNY summary + outlier warning

#### 3.3 Write commands (admin-only, confirmed)
- `/alloc <ex_order_id> <po_id>` (override allocation)
- `/split <ex_order_id> ...` (explicit split record)
- `/mark_cancelled <ex_order_id> [reason]`
- `/balance_set <USDT> [note]`

#### 3.4 Alert types
- New exchanger email ingested:
  - summary + suggested PO allocation + buttons:
    - Confirm
    - Choose PO…
    - Split…
    - Mark Cancelled
- Unmatched withdrawal older than X hours:
  - summary + “investigate” hint + button to show likely candidates
- Balance drift above threshold:
  - alert + button to set MANUAL snapshot
- Daily digest:
  - “green/yellow/red” status with anomalies + next actions

Acceptance criteria (M3):
- New exchanger email → allocated/confirmed in <30 seconds from Telegram.
- Operator can resolve 90% of anomalies without opening DB or markdown reports.


### Milestone M4 — Daily Close (“Supplier Funding Close”) (OPTIONAL but powerful)
**Goal:** one command to end-of-day supplier funding.

Tasks:
- Add `scripts/run_supplier_funding_close.py --date YYYY-MM-DD --strict`:
  - runs ingests
  - runs matching
  - runs allocation checks
  - generates reports
  - computes reconciliation diff
  - sends Telegram digest

Acceptance criteria (M4):
- One command produces updated DB + reports + Telegram close message.


## 5) Extra High-ROI Automations (reduce error)
1) Overpay guardrail:
   - if allocation would exceed total_cny + tolerance → hard block + require override reason

2) FX outlier alarm before big buys:
   - rolling median check on USDT/KZT and USDT/CNY
   - warn before executing a large funding action

3) “PO funding instruction generator”:
   - given a PO, bot outputs:
     - left_cny
     - equivalent usdt at recent rate
     - suggested P2P buy amount
     - copy-paste exchanger instruction text

4) Weekly funding plan digest:
   - unpaid POs + planned POs + needed USDT
   - push once/week in Telegram


## 6) Done Definition
Ledger supplier payments are “ops-grade” when:
- Reconciliation diffs are always explainable + audited
- Unmatched items are rare and automatically surfaced
- Humans only intervene for real anomalies
- Telegram is the default workflow UI
