# Agent 16 - Web Automation Kaspi Marketing Packet

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_16_wa_kaspi_marketing_packet_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_14_bank_source_route_closeout.md`
6. This starter prompt.

Role: produce or repair the accepted current-as-of Web_automation Kaspi Marketing source packet for Autonomous_business source `src_web_automation_kaspi_marketing_directapi`.

Current blocker:

- Existing accepted packet is `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`.
- It is structurally GREEN but only `as_of=2026-05-04`; it lacks `2026-06-13` coverage flags for `ACMEWEAR` and `STOREB`.

Scope:

- Work in `~/Docs/Web_automation`.
- Allowed writes: a new run folder under `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/`, source packet JSON, evidence summaries, closeout, and tests if needed.
- Forbidden writes: Autonomous_business `db/app.db`, Kaspi merchant mutations, ad bid/budget/product state changes, pricing uploads, external platform writes, Telegram, LaunchAgents, and customer/operator messages.
- Read-only external source acquisition is allowed only if existing tooling supports it without campaign/product/budget writes.

Packet acceptance contract:

- `schema_version=kaspi_marketing_source_freshness_packet.v1`
- `source_policy_key=src_web_automation_kaspi_marketing_directapi`
- `gate=GREEN`
- `as_of=2026-06-13`
- `ab_can_clear_src_web_automation_kaspi_marketing_directapi=true`
- `stores_required` and `stores_covered` exactly include `ACMEWEAR` and `STOREB`
- global `date_coverage_through=2026-06-13`
- global `date_coverage_through_2026_06_13=true`
- each store `latest_covered_date >= 2026-06-13`
- each store `date_coverage_through_2026_06_13=true`
- zero write counters for every packet-level and store-level write-safety field already enforced by AB parser
- referenced SQLite files pass integrity, referenced summaries are JSON-valid, and referenced closeouts prove no external writes

Validation from Autonomous_business side:

After creating the packet, use a copied DB or ask the orchestrator to rerun this command against AB. You may run it on a copied DB yourself:

```bash
cd ~/Docs/Autonomous_business
cp db/app.db exports/validation/agent16_wa_packet_ab_probe_20260613.db
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_policy_source_freshness.py --db exports/validation/agent16_wa_packet_ab_probe_20260613.db --as-of 2026-06-13 --run-id agent16_wa_packet_probe_20260613 --source-id src_web_automation_kaspi_marketing_directapi --backup-dir exports/validation/agent16_wa_packet_probe_backups --apply --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent16_wa_packet_ab_probe_20260613.db --as-of 2026-06-13 --strict --json
```

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include packet path, sha256, source folders, zero-write proof, and whether AB parser clears `src_web_automation_kaspi_marketing_directapi` on copied DB.
- Use `Gate: GREEN` only if the packet is current for 2026-06-13 and copied-DB AB materialization clears this source.
- Use `Gate: YELLOW` if no accepted current packet can be produced without missing credentials or external source access, but no unsafe writes happened.
- Use `Gate: RED` if any external write occurred or packet evidence is malformed after attempted repair.
