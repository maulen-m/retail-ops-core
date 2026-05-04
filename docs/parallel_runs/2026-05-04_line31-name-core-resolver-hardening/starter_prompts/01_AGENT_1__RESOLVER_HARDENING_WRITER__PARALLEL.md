# Agent 1: Resolver Hardening Writer

You are execution Agent 1 for the LINE31 name-core resolver hardening rollout.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/PLAN.md`
5. This starter prompt: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts/01_AGENT_1__RESOLVER_HARDENING_WRITER__PARALLEL.md`

## Role

You are the only write-capable execution agent for this rollout.

Do not revert unrelated dirty worktree changes. The repo already has unrelated parallel-session changes. Touch only files needed for this resolver hardening and `.claude/*` progress docs.

Do not production-apply DB writes. Any DB mutation must be temp-DB or dry-run unless the owner explicitly authorizes an apply gate later.

## Problem To Fix

Order `910294264` had wrong Google board `Kaspi_name_core = Женский_3в1_СИРЕНЕВЫЙ`, but its DB `sku_key` is olive LINE31:

```text
CL_OF_ARC_WM_LINE31_B-C-005_CARDAMOM-GREEN_J-C-005_CARDAMOM-GREEN_L-C-015_OLIVE-GREEN
```

The resolver currently chooses `(store_code, kaspi_offer_name)` before exact `sku_key`. The offer text `ACMEWEAR OF_LINE31_ST_SB_XL` is ambiguous across olive, espresso, and iris-purple LINE31 rows in `dim_kaspi_article_map`.

## Required Test-First Work

Write real failing tests before code changes. At minimum add coverage to `tests/test_kaspi_name_core_resolver.py` proving:

1. Exact `sku_key` beats conflicting store-offer mapping.
2. Ambiguous store-offer rows are not trusted when they disagree across multiple cores.
3. Forced/preferred core still wins.
4. Existing sku-family fallback behavior remains intact.

Recommended reproduction fixture:

- store: `ACMEWEAR`
- offer: `ACMEWEAR OF_LINE31_ST_SB_XL`
- olive sku: `CL_OF_ARC_WM_LINE31_B-C-005_CARDAMOM-GREEN_J-C-005_CARDAMOM-GREEN_L-C-015_OLIVE-GREEN`
- expected core: `Женский_3в1_ОЛИВКОВЫЙ`
- conflicting latest store-offer core: `Женский_3в1_СИРЕНЕВЫЙ`

After confirming the new test fails on current code, implement the smallest correct resolver change.

## Implementation Direction

Primary target:

- `~/Docs/Autonomous_business/core/utils/kaspi_name_core_resolver.py`

Possible dependent paths:

- `~/Docs/Autonomous_business/scripts/sync_google_ops_board.py`
- `~/Docs/Autonomous_business/tests/test_kaspi_name_core_resolver.py`
- `~/Docs/Autonomous_business/tests/test_sync_google_ops_board_contract.py`

Preferred semantics:

1. `preferred_core` / order override wins first.
2. Exact `sku_key` or sku-family mapping wins next.
3. `(store, kaspi_offer_name)` is used only if unambiguous.
4. Raw-offer fallback remains explicitly unsafe when used.

If implementing ambiguity filtering in `load_active_kaspi_name_core_maps`, ensure one store-offer key with multiple distinct active cores is excluded from `by_store_offer`.

## Verification

Run at least:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_kaspi_name_core_resolver.py tests/test_sync_google_ops_board_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile core/utils/kaspi_name_core_resolver.py scripts/sync_google_ops_board.py
scripts/check_no_db_tracked.sh
```

Also run one read-only proof command showing order `910294264` now resolves to `Женский_3в1_ОЛИВКОВЫЙ` under the DB map.

If docs are touched:

```bash
scripts/lint_docs.sh
```

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_line31-name-core-resolver-hardening/agent_1_execution_closeout.md`

Include:

- files changed;
- tests added before code changes;
- commands run and results;
- proof for order `910294264`;
- any remaining LINE31/API params follow-up;
- rollback steps;
- standalone final line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
