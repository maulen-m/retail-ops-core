# Agent 12 — Shipped-Freeze Cost-Basis Authority Scout

You are Agent12 in the green-path Phase-2 program. Work in:

`~/Docs/Autonomous_business`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent12_shipped_freeze_cost_basis_authority_scout_closeout.md`

Standalone closeout gate line required:

`Gate: GREEN|YELLOW|RED`

## Mission

Read-only scout the cost-basis mismatch that blocked Agent11. Determine which cost basis is authoritative for the 18 guarded `SHIPPED` on-delivery inventory moves:

- Agent9 expected stored `dim_sku.cogs_kzt` total: `53,898.00` KZT.
- Current guarded translator dry-run produced formula-landed total: `64,446.22` KZT because `_unit_cost_kzt_for_sku` prefers `base_cost_cny + weight_kg` formula when available.

Your output must decide whether a follow-up writer can safely apply the guarded translator result at `64,446.22` under existing repo contracts/tests, or whether owner approval / code contract change is required.

## Read-Only Inputs

Agent11 closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent11_shipped_freeze_guarded_writer_closeout.md`

Agent11 evidence:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_guarded_writer_20260614_093111`

Agent9 evidence:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_scout_20260614_20260614_091127`

Current DB SHA must remain:

`2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`

## Required Questions

Answer all of these explicitly:

1. Is `_unit_cost_kzt_for_sku` formula-first behavior an accepted current production contract, or only a local helper behavior?
2. Does any repo doc/test/validator prove that on-delivery inventory moves must use formula-landed COGS rather than stored `dim_sku.cogs_kzt` when both are present?
3. Does any repo doc/test/validator prove the opposite: that these shipped-freeze repair moves must use stored `dim_sku.cogs_kzt`?
4. Was Agent9's `53,898.00` expectation a scout calculation artifact, or a governed authority?
5. If formula-landed total `64,446.22` is authoritative, what exact follow-up writer contract is safe?
6. If stored total `53,898.00` is authoritative, what exact code/owner approval is needed before any write?
7. Should Agent11's allowlist/status guard patch remain, be amended, or be reverted?

## Required Evidence

Inspect at minimum:

- `scripts/translate_orders_to_cashflow_events.py`
- `tests/test_cashflow_translator.py`, especially cost-basis tests
- docs that mention order cashflow, COGS, landed COGS, stored legacy COGS, and inventory move valuation
- Agent9 and Agent11 dry-run evidence files listed above
- current DB rows for the involved `dim_sku` keys

Use `rg` first. Keep evidence under:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_cost_basis_authority_scout_20260614_<timestamp>/`

## Forbidden

No DB writes. No code edits. No dashboard/status/scoreboard edits. No COGS overrides. No stock writes. No external systems. No Telegram, LaunchAgents, Kaspi merchant, Repricer, pricing, workbooks, browser automation, customer/operator messages, or paid API usage.

## Closeout Requirements

Your closeout must include:

- `Gate: GREEN|YELLOW|RED`
- evidence folder path
- DB SHA start/final proof
- exact answer to the seven required questions
- a recommended next action:
  - `FOLLOWUP_WRITER_FORMULA_64446_SAFE`, or
  - `OWNER_APPROVAL_REQUIRED`, or
  - `CODE_CONTRACT_CHANGE_REQUIRED`, or
  - `STOP_REVERT_AGENT11_PATCH`
- if follow-up writer is safe, provide a precise expected writer contract: exact amount, exact command shape, exact validators, and stop rules
- if owner approval is required, provide the exact approval phrase needed

Gate guidance:

- `GREEN` only if existing repo authority clearly supports one exact follow-up path without owner input.
- `YELLOW` if evidence is useful but authority is ambiguous or owner approval is needed.
- `RED` if current evidence contradicts a safe write or reveals a code-contract bug that must be fixed before proceeding.
