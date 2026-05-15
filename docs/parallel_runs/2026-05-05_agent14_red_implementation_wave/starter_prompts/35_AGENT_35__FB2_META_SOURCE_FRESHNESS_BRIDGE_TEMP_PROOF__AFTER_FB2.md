# Agent 35 - FB2 Meta Source Freshness Bridge Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_fb2_meta_source_freshness_bridge_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_FB1_META_SOURCE.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_FB2_META_LIVE.md`
6. `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260505_acmewear_meta_live_refresh/FB2_ACMEWEAR_META_LIVE_READONLY_REFRESH_CLOSEOUT.md`
7. `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260505_acmewear_meta_live_refresh/meta_live_refresh_summary.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_32.md`
9. this starter prompt

## Mission

Temp-proof a fail-closed AB bridge that lets C3 source freshness consume the fresh FB2 Meta/Facebook read-only evidence packet.

FB2 proved the source window is refreshed and spend-free, but AB currently scans the Facebook_ads repo mostly through `docs` and `exports` directory hints. That means the fresh packet under `runs/ab_source_freshness_20260505_acmewear_meta_live_refresh/` can remain invisible unless AB learns to read source-freshness packets by schema, not by broad mtime.

Your job is to add the smallest safe bridge and prove it on a temp DB only.

## Coordination

You are not alone in the codebase. Agent 33 owns STOREB API order-entry temp apply, and Agent 34 owns ads active-scope semantics. Do not revert, overwrite, or broaden their edits.

Your likely write set is:

- `core/ops/policy_materialization_c3.py`
- `tests/test_policy_materialization_c3.py`
- maybe `tests/test_policy_registry_c3_contract.py` if a registry contract test is needed
- evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_evidence/`
- assigned closeout

If you need files outside this set, explain why in the closeout.

## Write Boundary

Allowed:

- code/tests for policy source-freshness packet parsing;
- temp DB copies under the Agent 35 evidence folder;
- assigned closeout and evidence files.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- live Meta/Facebook/Kaspi/Web_automation calls;
- broad directory mtime trust for all `runs`;
- treating missing Meta evidence as zero spend;
- clearing Meta source freshness from chat text or pane transcript alone.

## Required Behavior

For `src_facebook_ads_external_ads`, AB may treat the source as fresh only when it finds a schema-valid Meta source-freshness packet that proves:

- `gate == "GREEN"`;
- `ab_can_clear_src_facebook_ads_external_ads == true`;
- all requested dates were successfully fetched;
- every requested date has `source_status == "SUCCESS"`;
- every requested date has `clears_source_freshness == true`;
- raw evidence paths exist for the refreshed dates;
- `platform_writes_occurred == false`;
- `budget_status_campaign_adset_ad_writes_occurred == false`;
- `autonomous_business_writes_performed == false`;
- `deterministic_purchase_attribution_claimed == false`;
- `any_spend_found == false` for this no-spend bridge.

If spend is found, do not silently pass. Mark source as blocked or partial and say an external-ads spend ingestion lane is required.

Do not overfit to one timestamp. It is acceptable to prefer the latest schema-valid `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json` under a narrowly named Facebook_ads source-freshness run folder, but the parser must fail closed on malformed or unsafe packets.

## Required Work

1. Write tests first:
   - a valid FB2-style packet clears `src_facebook_ads_external_ads`;
   - missing packet remains stale/missing;
   - non-GREEN packet fails closed;
   - incomplete date coverage fails closed;
   - platform/ad writes flagged true fails closed;
   - `any_spend_found=true` fails closed for this no-spend bridge.
2. Implement the smallest bridge in the policy source materializer.
3. Copy Agent 32's temp DB to a new Agent 35 temp DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/agent32_ads_fresh_temp_20260504.db`

4. Materialize source freshness on the Agent 35 temp DB using the FB2 packet.
5. Prove `src_facebook_ads_external_ads` is no longer blocking in `v_source_freshness_current`.
6. Preserve and enumerate any unrelated strict C3 source-freshness blockers that remain.

## Required Validation Commands

Run the smallest relevant gates and record exact commands/results:

```bash
python3 -m py_compile core/ops/policy_materialization_c3.py tests/test_policy_materialization_c3.py
pytest -q tests/test_policy_materialization_c3.py tests/test_policy_registry_c3_contract.py
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/agent32_ads_fresh_temp_20260504.db 'PRAGMA integrity_check;'
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 python3 scripts/materialize_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_evidence/agent35_fb2_meta_bridge_temp_20260504.db --as-of 2026-05-04 --run-id agent35_fb2_meta_bridge --apply --backup-dir ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_evidence/backups --json
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_evidence/agent35_fb2_meta_bridge_temp_20260504.db --as-of 2026-05-04 --strict --json
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_35_evidence/agent35_fb2_meta_bridge_temp_20260504.db 'PRAGMA integrity_check;'
bash scripts/lint_docs.sh
```

If strict source-freshness validation still fails because of unrelated source rows, keep the gate YELLOW and list them. The success criterion for this agent is specifically that `src_facebook_ads_external_ads` is schema-cleared without weakening fail-closed behavior.

## Expected Gate

GREEN is allowed only if:

- tests pass;
- `src_facebook_ads_external_ads` becomes non-blocking on the temp DB;
- invalid or unsafe packets fail closed;
- no production DB or external write occurred;
- strict source freshness has no unrelated blockers.

YELLOW is correct if:

- the Meta source bridge works and is tested, but strict C3 still has unrelated blockers.

RED is correct if:

- the bridge requires broad mtime trust, ignores missing evidence, treats unknown spend as zero, or weakens fail-closed publication rules.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- temp DB path used;
- before/after `src_facebook_ads_external_ads` status;
- remaining unrelated source freshness blockers;
- explicit production apply status.
