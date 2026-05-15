# Agent756 - Autonomous Business Ads Adoption Mapper

You are Agent756. Your task is a read-only first-pass mapping from the current Autonomous Business ads validators and Cash Risk Daily proof to a possible Web_automation adoption contract.

Gate target: `GREEN`, `YELLOW`, or `RED`.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_756_ab_ads_adoption_mapper_closeout.md`

Assigned evidence directory:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_756_ab_ads_adoption_mapper_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/WEB_AUTOMATION_ADS_ADOPTION_DISCOVERY_CONTROL_20260510_215225.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_20260510_200936.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
6. `~/Docs/Autonomous_business/exports/validation/option_c_validate_only/cash_risk_daily_20260510_180607/04_validator_outputs/ads_sidecar_readiness/2026-05-04/ads_sidecar_readiness_report.json`
7. `~/Docs/Autonomous_business/exports/validation/option_c_validate_only/cash_risk_daily_20260510_180607/04_validator_outputs/ads_offer_universe/ads_offer_universe_report.json`
8. `~/Docs/Web_automation/AGENTS.md`
9. `~/Docs/Web_automation/Docs/kaspi_marketing_local.md`
10. `~/Docs/Web_automation/Docs/marketing_watcher_plan.md`
11. this assigned starter prompt

You are not required to wait for Agents754 or 755. Do not read their reports before writing your own first-pass closeout.

## Scope

Inventory and map:

- Current AB ads validator outputs in the Cash Risk Daily proof.
- AB scripts/config/docs found by `rg` for `ADS_SOURCE_STALE`, `ads_sidecar_readiness`, `ads_offer_universe`, `campaign_max_date`, and `source_fresh`.
- Web_automation local marketing source contracts from docs only, enough to propose an adoption boundary.

## Hard Stoplines

- Do not run live fetches.
- Do not open browser or log in.
- Do not read `.env`, cookies, storage state, browser profile files, or secrets.
- Do not write inside `~/Docs/Web_automation`.
- Do not write inside `~/Docs/Autonomous_business` except if `agent_complete.py` writes completion metadata.
- Do not mutate DBs, workbooks, schedulers, LaunchAgents, ad platforms, Kaspi, Google, bank, or external systems.
- Do not hide `ADS_SOURCE_STALE`.
- Do not weaken `23` or `252` warning visibility.
- Do not convert copied-DB validate-only proof into production authority.

## Deliverable

Write the assigned closeout with:

- standalone line `Gate: GREEN` if there is a clear design-only adoption path;
- `Gate: YELLOW` if adoption requires live-readonly proof, source-contract amendment, or CodeCaptain review;
- `Gate: RED` if adoption is unsafe or blocked.

Required sections:

- `Read Scope`
- `Current AB Ads Blocker`
- `Current Coverage Versus Freshness Distinction`
- `Candidate Web_automation Inputs`
- `Proposed AB Adapter Contract`
- `Minimum Safe Next Lane`
- `CodeCaptain Review Need`
- `Risks Or Unknowns`
- `Recommended Next Step`

Prefer exact file paths and line references. Keep the closeout compact but evidence-backed.
