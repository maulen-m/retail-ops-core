# Agent 67 - Source And Ads Freshness Root-Cause Diagnosis Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_source_ads_freshness_root_cause_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_evidence/`

## Mission

Explain the Agent65 policy source-freshness and ads-validator failures.

CodeCaptain confirmed Agent65 is `RED` and requires ads/source-freshness repair evidence before any new owner-request preflight. Your job is to identify exact root causes and the safest repair path, not to repair production.

This is a read-only diagnosis lane. It may run validators in read-only/dry-run mode and write outputs only under your evidence folder.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT65_RED_PREFLIGHT_REVIEW_20260507.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-07/170703_TASK-000_codecaptain-agent65-red-preflight-review/Answer/Code_Captain_2026-05-07_17_50_00.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_owner_request_preflight_activation_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/PINNED_VALIDATOR_MATRIX.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/validator_logs/`
11. `~/Docs/Autonomous_business/scripts/validate_policy_source_freshness.py`
12. `~/Docs/Autonomous_business/scripts/materialize_policy_source_freshness.py`
13. `~/Docs/Autonomous_business/scripts/validate_ads_sidecar_readiness.py`
14. `~/Docs/Autonomous_business/scripts/validate_ads_offer_universe_coverage.py`
15. `~/Docs/Autonomous_business/scripts/validate_ads_spend_reality.py`
16. Your assigned starter prompt.

Do not read Agent66's report before publishing your own first-pass closeout.

## Current Known Failed Validators From Agent65

- `validate_policy_source_freshness.py --as-of 2026-05-04 --strict`: missing freshness result for 8 required sources.
- `validate_ads_sidecar_readiness.py`: `ADS_DATA_UNAVAILABLE`, `ADS_CANONICAL_STALE`, `ADS_REFRESH_COVERAGE_MISSING`.
- `validate_ads_offer_universe_coverage.py`: `failing_month_store_pairs=4`, `spend_reality_fail_pairs=6`, `missing_sold_offers=19`.
- `validate_ads_spend_reality.py`: `spend_reality_fail_pairs=6`.

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_source_ads_freshness_root_cause_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit repo files.
- Do not run `--apply`.
- Do not refresh live APIs, browser sessions, banks, Kaspi, ads platforms, Google, Web_automation, or external systems.
- Do not change external repos.
- Do not ask the owner for authorization.
- Do not production-apply.
- Do not weaken validators or treat missing ads as zero spend.

## Required Analysis

Produce `SOURCE_ADS_FRESHNESS_ROOT_CAUSE_REPORT.md` in the assigned evidence folder.

The report must include:

- READCHECK with exact files read.
- Current production DB/workbook SHA at analysis time.
- Policy source freshness: stored-row diagnosis versus dry-run/current-code diagnosis for `--as-of 2026-05-04`.
- Source-by-source table for missing/stale/future/blocked freshness sources, including source owner, expected source path, root cause, repair action, and whether owner input is required.
- Ads sidecar readiness root cause: whether canonical ads tables are absent, empty, stale, unmapped, out-of-scope, or validator-contract blocked.
- Ads offer universe coverage root cause: missing sold offers, affected store/month pairs, and whether this is data gathering, mapping, scope config, or quarantine issue.
- Ads spend reality root cause: affected store/month pairs and whether values are unavailable, stale, implausible, or missing source evidence.
- Exact minimal repair sequence for later agents, split into temp-only proof steps and potential production apply-contract steps.
- Explicit statement of what can run before Agent66 finishes and what must wait for drift baseline decision.

## Suggested Read-Only Commands

Adapt safely as needed. Output files must go under your assigned evidence folder.

```bash
date '+%Y-%m-%d %H:%M:%S %z %Z'
shasum -a 256 ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db '.schema source_freshness_result'
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db 'select * from source_freshness_result order by source_id, as_of_date, run_id;'
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_ads_sidecar_readiness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --output-root <assigned_evidence_folder>/ads_sidecar_readiness --strict
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_ads_offer_universe_coverage.py --db-path ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <assigned_evidence_folder>/ads_offer_universe --strict
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_ads_spend_reality.py --db-path ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <assigned_evidence_folder>/ads_spend_reality --strict
```

`materialize_policy_source_freshness.py` is dry-run unless `--apply` is passed. You may run it without `--apply` only if you record DB SHA before and after and confirm no DB mutation occurred:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/materialize_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --run-id agent67_readonly_probe --json
```

Do not run this command if code inspection suggests it could write without `--apply`.

## Gate Semantics

`GREEN`:

- Every source/ads blocker has an evidence-backed root cause and a concrete repair path.
- No source ambiguity blocks Agent68 planning.
- No production/workbook/external mutation occurred.

`YELLOW`:

- Most blockers are classified, but some require owner/external-source data or must wait for Agent66 drift/baseline decision.

`RED`:

- Source/ads failures cannot be interpreted safely.
- A required repair would need immediate live/external data gathering not authorized here.
- Any forbidden mutation occurred.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN/YELLOW/RED` line;
- exact files written;
- exact commands run;
- current boundary summary;
- source-freshness blocker table;
- ads-readiness/universe/spend blocker table;
- repair sequence proposal;
- whether Agent68 may launch from the source/ads perspective, must wait, or remains blocked;
- evidence file list;
- plain-English owner clarification needed, if any.
