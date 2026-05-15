# Agent 72E / Launcher 728 - Existing Command Gate Audit And Manifest Prep

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72e_existing_command_gate_audit_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72e_evidence/`

Parallel group:

`agent72b_e_write_gate_hardening`

Dependency:

Run only after Agent72A closeout is reviewed as non-RED.

## Mission

Audit and prepare the existing non-wrapper command-family gates so Agent729 can perform one clean serialized manifest/contract integration after Agents725-727 finish. This lane should verify existing scripts and produce exact manifest/command-shape recommendations. Do not edit shared manifest/config in parallel.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others. Own only evidence/closeout files unless a tiny focused test is strictly required for this audit.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_contract_hardening_write_gate_verification_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/WRITE_GATING_VERIFICATION.tsv`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72a_evidence/COMMAND_FAMILY_FINALIZATION.md`
9. `~/Docs/Autonomous_business/config/write_side_gating_manifest.yaml`
10. `~/Docs/Autonomous_business/scripts/validate_write_side_gating.py`

Also inspect the existing command-family scripts that Agent72A marked as missing manifest coverage or requiring corrected production gate shape.

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72e_existing_command_gate_audit_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72e_evidence/**`
- optional focused tests only if needed to prove a specific existing gate, but avoid shared code/config edits unless absolutely necessary

Forbidden:

- Do not edit `config/write_side_gating_manifest.yaml`; Agent729 owns final manifest integration.
- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers, external repos, browser, Kaspi/API, Google, Meta, banks, Web_automation, or live workbooks.
- Do not ask owner for authorization.
- Do not production-apply or activate any owner phrase.

## Required Work

Produce:

1. `EXISTING_COMMAND_GATE_AUDIT.tsv`
   - For each existing non-wrapper command in Agent72A's family, list script path, env gates required, production-specific gates if any, `--apply` requirement, backup behavior, idempotency, focused tests, current manifest coverage, and exact recommended manifest row.
2. `PRODUCTION_COMMAND_SHAPE_PATCH.md`
   - Correct Agent72 command shapes for:
     - `scripts/materialize_ads_campaign_product_daily.py` must include `ALLOW_PRODUCTION_C3_ADS_SOURCE_WRITE=1` when targeting production `db/app.db`.
     - `scripts/recover_order_entries_from_evidence.py` must include `ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE=1` when targeting production `db/app.db`.
     - strict `23` STOREB production quarantine must use `scripts/apply_storeb_product_identity_quarantine_production_safe.py`, not the temp materializer.
     - policy freshness, sales fact, order-status, stock-ledger, and cashflow translator manifest rows needed for final integration.
3. `MANIFEST_INTEGRATION_TODO.yaml`
   - A proposed YAML fragment or exact list of rows for Agent729 to add after wrapper agents finish.

Run at minimum:

```bash
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_write_side_gating.py tests/test_materialize_ads_campaign_product_daily.py tests/test_recover_order_entries_from_evidence.py tests/test_storeb_product_identity_quarantine_prod_wrapper.py
```

If a listed test file does not exist or fails for unrelated reasons, record exact evidence and classify the gate honestly.

## Closeout

Write the closeout with:

- READCHECK
- evidence files produced
- tests run and outputs
- exact manifest rows recommended
- residual blockers
- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`

Gate GREEN only if existing command-family gate shapes are clear enough for Agent729 to integrate without guessing.
