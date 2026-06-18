# Agent 5 - Meta API Factory Smoke

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Business_3/Facebook_ads/exports/validation/meta_api_live_public_completion_webui_20260606/META_API_LIVE_PUBLIC_COMPLETION_WEBUI_CLOSEOUT.md`
6. This assigned starter prompt.

Workdir:

`~/Docs/Business_3/Facebook_ads`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent5_meta_api_factory_smoke_closeout.md`

Assigned evidence root:

`~/Docs/Business_3/Facebook_ads/exports/validation/line31_expert_plan_completion_20260606/agent5_meta_api_factory_smoke`

## Task

Repair/reconcile the Meta API smoke guard to the owner-confirmed current LINE31 ad set budget `5500` Meta minor units, then execute exactly one bounded adcreative smoke only if fresh preflight passes.

Important:

- The Meta app public blocker was reportedly fixed by WebUI, but must be proven by the smoke.
- The previous smoke preflight blocked because it expected old budget `3093` while current API readback was `5500`.
- This lane is approved for one unattached non-delivering adcreative smoke only, not a campaign/adset/ad/creative-for-delivery write.

Prefer flow:

1. Run current read-only LINE31 snapshot and primary API preflight.
2. Run smoke preflight with current budget guard `5500`; if scripts/tests need a local budget-guard reconciliation, patch only the narrow local script/test/config needed and run focused tests.
3. If preflight emits evidence lock and SHA, create an approval text file containing the owner approval from the plan plus the fresh lock path/SHA.
4. Execute:

```bash
python3 scripts/preflight_meta_app_mode_adcreative_smoke.py --execute-approved-smoke --approved-preflight-lock <fresh-lock-path> --approved-preflight-sha256 <fresh-lock-sha> --approval-text-file <approval-text-file> --output-root exports/validation/line31_expert_plan_completion_20260606/agent5_meta_api_factory_smoke --run-id execute_smoke --json
```

5. Read back the creative and confirm no ad object was created or linked to it.
6. Confirm LINE31 campaign/adset/ad/budget/status/URL/CTA state did not drift.

Run focused tests if code/config changes:

```bash
pytest -q tests/test_meta_api_primary_contract.py tests/test_meta_app_mode_adcreative_smoke.py tests/test_snapshot_line31_current_meta_state.py
scripts/check_no_secrets.sh
git diff --check
```

## Forbidden

Do not create/update campaigns, ad sets, ads, budgets, statuses, targeting, landing URLs, delivery creatives, website deploys, Kaspi/WebUI/API writes, CRM writes, price changes, stock changes, cash movement, supplier payment, PO commitment, production DB/workbook writes, scheduler/source-pointer changes, owner publication, internal Kaspi campaign changes, or unrelated external action.

## Gate

`GREEN` if the app-public smoke succeeds, exactly one unattached non-delivering adcreative object is created/read back, no ad object is created, and LINE31 state is unchanged.

`YELLOW` if preflight blocks or Meta rejects the bounded smoke without LINE31 state drift.

`RED` if an ad object is created, LINE31 state drifts, a forbidden write occurs, or secrets leak.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, fresh preflight evidence path/SHA, smoke result, created adcreative id if any, explicit no-ad-created assertion, LINE31 state no-drift assertion, tests/checks, and boundary attestation.
