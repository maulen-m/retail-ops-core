# Agent 38 - Web Automation Kaspi Marketing Source Packet Standardization

Assigned closeout:

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/WA_AGENT_38_KASPI_MARKETING_SOURCE_PACKET_STANDARDIZATION_CLOSEOUT.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Web_automation/AGENTS.md`
2. `~/Docs/Web_automation/Docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
4. this starter prompt

## Mission

Create one strict, machine-readable Kaspi Marketing source-freshness packet from the accepted Web_automation read-only evidence so Autonomous Business can later consume it fail-closed.

## Write Boundary

Allowed:

- write only under `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/`;
- read existing Web_automation evidence folders;
- assigned closeout.

Forbidden:

- Autonomous_business writes;
- live Kaspi/Marketing/API/browser calls;
- campaign/bid/budget/product-state changes;
- editing existing evidence packets.

## Required Inputs

Use these existing evidence roots:

- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/`

## Required Output Packet

Write:

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`

The packet must include at minimum:

- `gate: "GREEN"` only if every strict requirement passes;
- `as_of: "2026-05-04"`;
- `ab_can_clear_src_web_automation_kaspi_marketing_directapi: true` only if safe;
- store coverage for `ACMEWEAR` and `STOREB`;
- date coverage through `2026-05-04`;
- paths and SHA-256 hashes of every source SQLite used;
- paths and SHA-256 hashes of every source evidence summary consumed;
- explicit `external_write_operations: 0`;
- explicit `ad_platform_write_operations: 0`;
- explicit `campaign_bid_budget_product_state_changes: 0`;
- explicit `autonomous_business_writes: 0`;
- explicit `read_only_external_operations: true` or equivalent evidence;
- `issues: []` only if no issues exist.

If the packet cannot be strict `GREEN`, write a `YELLOW` packet with exact missing fields and do not claim AB can clear the source.

## Required Validation

Run local JSON/SQLite/hash checks. At minimum:

```bash
python3 -m json.tool ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json >/tmp/agent38_packet_json_check.txt
sqlite3 -readonly ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite 'PRAGMA integrity_check;'
sqlite3 -readonly ~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite 'PRAGMA integrity_check;'
```

Also validate that referenced files exist and hashes match what the packet records.

## Expected Gate

`GREEN` only if the packet is strict enough for AB to consume fail-closed.

`YELLOW` if useful evidence exists but one or more source packets cannot prove strict no-write/coverage/hash requirements.

`RED` if any live/external write occurred, evidence is malformed, or the packet overclaims freshness.
