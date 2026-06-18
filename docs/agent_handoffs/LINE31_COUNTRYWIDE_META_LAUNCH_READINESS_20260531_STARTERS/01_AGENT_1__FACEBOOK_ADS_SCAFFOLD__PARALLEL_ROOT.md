# Agent 1 Starter - Facebook_ads LINE31 Meta Scaffold

You are Agent 1. Your lane prepares a dry-run LINE31 countrywide Meta campaign scaffold and monitoring contract. No Meta or external write is authorized.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/docs/00_CORE/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/01_AGENT_1__FACEBOOK_ADS_SCAFFOLD__PARALLEL_ROOT.md`

## Source Inputs

Read:

1. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/Strategy_expert_31.05.2026_20_33_01.md`
2. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/META_CAMPAIGN_SPEC.csv`
3. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/DAILY_CASHFLOW_REPORTING_SPEC.csv`
4. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/LAUNCH_GATES_AND_MONITORING_RULES.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/OWNER_APPROVAL_PHRASES.md`

## Scope

Allowed writes:

- repo-local docs/scripts/tests/config in `~/Docs/Business_3/Facebook_ads` only when they are dry-run/scaffold/readiness surfaces;
- local generated evidence under `~/Docs/Business_3/Facebook_ads/exports/validation/line31_countrywide_meta_launch_readiness_20260531/`;
- assigned closeout under the shared handoff folder.

Forbidden:

- any Meta API/UI mutation;
- campaign/ad/adset/creative/budget/status/objective/custom-conversion publish or edit;
- Kaspi/API/WebUI/CRM writes;
- website deploys;
- production DB/workbook/source-pointer/scheduler/cash/PO/stock/price actions.

## Task

Create the Facebook_ads LINE31 campaign scaffold lane tailored to the existing repo.

Required work:

- identify current repo naming, UTM, measurement, and dashboard conventions;
- produce a local LINE31 countrywide campaign scaffold using one campaign, one broad women ad set, Instagram-only placements, LPV optimization first, ViewContent upgrade later, and HighIntent reporting only;
- create or update dry-run validation surfaces so the scaffold can be checked without publishing;
- create a creative manifest placeholder that waits for final owner-approved video assets;
- encode stoplines: zero server redirects after 8k-10k KZT spend, wrong route, tracking failure, cash red, LINE31 stock below 7-day cover;
- keep attribution labels separate: Meta traffic truth, website truth, redirect truth, Kaspi order truth, directional attribution only while internal LINE31 Kaspi is active.

## Required Outputs

Write these under your local evidence folder:

- `line31_meta_campaign_scaffold.csv`
- `line31_utm_contract.md`
- `line31_creative_manifest_template.csv`
- `line31_meta_monitoring_rules.md`
- `line31_facebook_ads_repo_gap_report.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent1_facebook_ads_scaffold_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact files created/changed;
- validation commands run;
- explicit confirmation that no Meta live write was performed.

Use `GREEN` only if the scaffold and validations are complete under no-live-write rules. Use `YELLOW` if some repo convention or live freshness source is missing. Use `RED` for any mutation attempt or unsafe attribution claim.
