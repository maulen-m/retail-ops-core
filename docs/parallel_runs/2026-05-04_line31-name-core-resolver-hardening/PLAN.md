# LINE31 Name-Core Resolver Hardening Plan

Date: 2026-05-04

Repo: `~/Docs/Autonomous_business`

Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_line31-name-core-resolver-hardening`

## Purpose

Fix the LINE31 Google Ops Board `Kaspi_name_core` mis-resolution that made order `910294264` display as `Женский_3в1_СИРЕНЕВЫЙ` even though its canonical SKU is the olive-green LINE31 set.

## Confirmed Root Cause

- `fact_orders_kaspi.order_id = 910294264` has olive LINE31 `sku_key`.
- `dim_kaspi_article_map` contains the same `(store_code, kaspi_offer_name)` key, `ACMEWEAR / ACMEWEAR OF_LINE31_ST_SB_XL`, mapped to olive, espresso, and iris-purple LINE31 cores.
- `core/utils/kaspi_name_core_resolver.py` currently resolves by `(store, offer text)` before exact `sku_key`.
- The latest ambiguous store-offer row is purple, so the Google board resolved the olive order to `Женский_3в1_СИРЕНЕВЫЙ`.
- `fact_order_entries_kaspi` currently has no row for `910294264`, so exact line-entry offer identity was not available during board publish.

## Agent Topology

Only two agents are used to keep the rollout small.

Agent 1: writer/execution

- Writes real failing regression tests first.
- Implements resolver hardening.
- Adds/updates validations needed to prevent ambiguous LINE31 store-offer fallback.
- Runs targeted gates.
- Updates repo-local `.claude/*` state and execution closeout.

Agent 2: read-only analyst

- Audits LINE31 offer identity coverage and product-offer params sync paths.
- Does not modify repo files or DB.
- Publishes a source-backed LINE31 coverage report for Agent 1 and future follow-up work.

## Launch Order

Agent 1 and Agent 2 may start in parallel because only Agent 1 writes shared repo state.

Agent 1 should not perform production DB writes. Any DB repair must be dry-run or temp-DB only unless the owner explicitly authorizes an apply gate later.

Agent 1 may complete the resolver/test fix without waiting for Agent 2. If Agent 2 finds a blocker that changes the resolver contract, Agent 1 should incorporate it before final closeout.

## Required Fix Contract

1. Exact `sku_key` mapping must win before ambiguous `(store, kaspi_offer_name)` mapping.
2. `(store, kaspi_offer_name)` must not be trusted when active mappings disagree across multiple `kaspi_name_core` values or LINE31 SKU keys.
3. Regression must reproduce order `910294264` semantics:
   - offer text: `ACMEWEAR OF_LINE31_ST_SB_XL`
   - exact SKU: `CL_OF_ARC_WM_LINE31_B-C-005_CARDAMOM-GREEN_J-C-005_CARDAMOM-GREEN_L-C-015_OLIVE-GREEN`
   - conflicting latest store-offer map: `Женский_3в1_СИРЕНЕВЫЙ`
   - expected resolved core: `Женский_3в1_ОЛИВКОВЫЙ`
4. Existing explicit forced/order overrides must still win over all map-derived values.
5. Unsafe raw-offer fallback behavior must remain explicit and test-covered.

## Verification Gates

At minimum, Agent 1 must run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_kaspi_name_core_resolver.py tests/test_sync_google_ops_board_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile core/utils/kaspi_name_core_resolver.py scripts/sync_google_ops_board.py
scripts/check_no_db_tracked.sh
```

If docs are touched:

```bash
scripts/lint_docs.sh
```

If the execution agent adds a validator script, include its targeted tests and at least one command proving order `910294264` now resolves to olive in read-only mode.

## Closeout Files

Agent 1 closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_line31-name-core-resolver-hardening/agent_1_execution_closeout.md`

Agent 2 closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_line31-name-core-resolver-hardening/agent_2_line31_identity_audit.md`

Orchestrator review:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_line31-name-core-resolver-hardening/ORCHESTRATOR_REVIEW.md`

Each closeout must include a standalone final line:

```text
Gate: GREEN
```

Use `YELLOW` or `RED` if anything material remains unresolved.
