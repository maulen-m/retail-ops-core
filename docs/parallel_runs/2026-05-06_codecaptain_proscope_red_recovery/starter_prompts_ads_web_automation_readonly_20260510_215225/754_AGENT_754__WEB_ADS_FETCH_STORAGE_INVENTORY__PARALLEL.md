# Agent754 - Web Automation Ads Fetch/Storage Inventory

You are Agent754. Your task is a read-only first-pass inventory of Web_automation Kaspi Marketing ads fetch and storage capabilities that may help Autonomous Business resolve `ADS_SOURCE_STALE`.

Gate target: `GREEN`, `YELLOW`, or `RED`.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_754_web_ads_fetch_storage_inventory_closeout.md`

Assigned evidence directory:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_754_web_ads_fetch_storage_inventory_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/WEB_AUTOMATION_ADS_ADOPTION_DISCOVERY_CONTROL_20260510_215225.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_20260510_200936.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
6. `~/Docs/Web_automation/AGENTS.md`
7. `~/Docs/Web_automation/Docs/00_START_HERE.md`
8. `~/Docs/Web_automation/Docs/kaspi_marketing_local.md`
9. this assigned starter prompt

You are not required to wait for Agents755 or 756. Do not read their reports before writing your own first-pass closeout.

## Scope

Inventory only these Web_automation areas unless evidence directly points elsewhere:

- `web_auto/kaspi_marketing.py`
- `web_auto/cli.py` sections for `kaspi-marketing`
- `Docs/kaspi_marketing_local.md`
- relevant configs/docs surfaced by `rg` for `kaspi-marketing`, `fetch-campaigns`, `campaign_daily_current`, and `campaign_product_daily_current`

## Hard Stoplines

- Do not run live fetches.
- Do not open browser or log in.
- Do not read `.env`, cookies, storage state, browser profile files, or secrets.
- Do not write inside `~/Docs/Web_automation`.
- Do not write inside `~/Docs/Autonomous_business` except if `agent_complete.py` writes completion metadata.
- Do not mutate DBs, workbooks, schedulers, LaunchAgents, ad platforms, Kaspi, Google, bank, or external systems.
- Do not treat review-only proof as owner-publication or production authority.

## Deliverable

Write the assigned closeout with:

- standalone line `Gate: GREEN` if Web_automation fetch/storage is clearly reusable for an AB design-only adapter;
- `Gate: YELLOW` if it is promising but needs explicit missing evidence or live-readonly proof;
- `Gate: RED` if reuse is unsafe or blocked.

Required sections:

- `Read Scope`
- `Fetch Entrypoints`
- `SQLite Tables And Columns`
- `Run Artifacts`
- `Multi-Store Or Store Identity Handling`
- `Secrets And Credential Boundaries`
- `Reusable Pieces For Autonomous Business`
- `Risks Or Unknowns`
- `Recommended Next Step`

Prefer exact file paths and line references. Keep the closeout compact but evidence-backed.
