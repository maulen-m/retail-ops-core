# Agent 17 - Meta Source Packet Boundary

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_17_meta_source_packet_boundary_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_14_bank_source_route_closeout.md`
6. This starter prompt.

Role: determine whether `src_facebook_ads_external_ads` can be cleared with an accepted no-write Meta/Facebook source-freshness packet for 2026-06-13.

Hard boundary:

- Meta/Instagram ad control is untouchable.
- No budget, campaign, adset, ad, creative, status, attribution, or deterministic purchase-attribution writes.
- No platform writes at all.
- If read-only API access is not already available, stop as YELLOW with exact missing-auth evidence. Do not ask the owner mid-run.

Current blocker:

- AB accepts `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json` under `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_*`.
- Existing accepted packet only covers through `2026-05-04`.
- AB requires `dates_requested`, `dates_successfully_fetched`, `date_results`, write-safety booleans, raw evidence paths under the packet run, and `any_spend_found=false`.

Scope:

- Work in `~/Docs/Business_3/Facebook_ads`.
- Allowed writes: a new read-only run folder under `runs/ab_source_freshness_*`, raw read-only evidence, packet JSON, closeout, and tests if needed.
- Forbidden writes: Autonomous_business `db/app.db`, ad platform writes, Web_automation writes, Kaspi writes, Telegram, LaunchAgents, customer/operator messaging.

Acceptance contract from AB parser:

- packet filename: `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json`
- folder name starts with `ab_source_freshness_` and includes `meta` or `facebook`
- `gate=GREEN`
- `ab_can_clear_src_facebook_ads_external_ads=true`
- `dates_requested` are valid dates through `2026-06-13`
- `dates_successfully_fetched` exactly matches requested dates
- every `date_results` row has `source_status=SUCCESS` and `clears_source_freshness=true`
- `source_freshness_cleared_by_date[date]=true` for every requested date
- raw evidence paths exist and are inside the packet run folder
- `platform_writes_occurred=false`
- `budget_status_campaign_adset_ad_writes_occurred=false`
- `autonomous_business_writes_performed=false`
- `deterministic_purchase_attribution_claimed=false`
- `any_spend_found=false`

Validation from Autonomous_business side:

After creating the packet, use a copied DB or ask the orchestrator to rerun this command against AB. You may run it on a copied DB yourself:

```bash
cd ~/Docs/Autonomous_business
cp db/app.db exports/validation/agent17_meta_packet_ab_probe_20260613.db
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_policy_source_freshness.py --db exports/validation/agent17_meta_packet_ab_probe_20260613.db --as-of 2026-06-13 --run-id agent17_meta_packet_probe_20260613 --source-id src_facebook_ads_external_ads --backup-dir exports/validation/agent17_meta_packet_probe_backups --apply --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent17_meta_packet_ab_probe_20260613.db --as-of 2026-06-13 --strict --json
```

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include packet path, sha256, raw evidence path list, no-write booleans, and AB copied-DB result.
- Use `Gate: GREEN` only if AB parser clears `src_facebook_ads_external_ads` on copied DB and no spend/write issue is present.
- Use `Gate: YELLOW` if no current accepted packet can be produced due missing auth, missing source, spend found, or intentionally retained Meta boundary.
- Use `Gate: RED` if any ad-platform write occurred or packet claims cannot be trusted.
