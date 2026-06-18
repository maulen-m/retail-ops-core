# Agent 4: Ads Truth Gate Proof

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
5. `~/Docs/Autonomous_business/docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`
8. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent4_ads_truth_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent4_ads_truth_evidence`

## Task

Build read-only or copied-temp evidence for the Ads Truth Gate.

Preserve these rules:

- STOREB business identity is not UNIVERSAL access identity.
- Missing spend is a gap, not zero.
- No ad-platform write, bid, budget, campaign, or external account change is authorized.

Produce:

- `ADS_SOURCE_FRESHNESS_PACKET.json`
- `ADS_PRODUCT_CODE_MAPPING_MATRIX.csv`
- `ADS_UNMAPPED_POSITIVE_SPEND.csv`
- `ADS_SPEND_REALITY_REPORT.json`
- `ADS_OFFER_UNIVERSE_REPORT.json`

Run where safe:

```bash
python3 scripts/validate_ads_source_packet_contract.py --strict
python3 scripts/validate_ads_sidecar_readiness.py --strict
python3 scripts/validate_ads_offer_universe_coverage.py --strict
python3 scripts/validate_ads_spend_reality.py --strict
```

## Boundary

Read-only or copied-temp only. You may inspect local Web_automation evidence if needed and authorized by local docs, but do not mutate Web_automation, browser profiles, cookies, storage state, ad platforms, source pointers, production DB, workbook, or schedulers.

## Gate Guidance

Use `Gate: GREEN` only if ads validators pass for the declared scope and unmapped positive spend is zero or accepted under contract.

Use `Gate: YELLOW` if source freshness, mapping, offer universe, Meta, STOREB, or positive spend blockers remain.

Use `Gate: RED` if missing spend is zeroed, identities are mixed, or any external write path is touched.
