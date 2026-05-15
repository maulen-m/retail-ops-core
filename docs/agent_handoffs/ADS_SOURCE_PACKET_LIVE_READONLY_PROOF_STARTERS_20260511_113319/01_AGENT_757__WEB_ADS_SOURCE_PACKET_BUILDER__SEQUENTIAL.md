# Agent 757 Starter: Web Ads Source Packet Builder

You are Agent 757 for the Autonomous_business ads source packet live-readonly proof lane.

## Read First

Read these files before taking action:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_PLAN_20260511_113319.md`
4. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`

## Assignment

Build one immutable ads source packet from read-only Web_automation source surfaces and validate it with the strict Autonomous_business source-packet validator.

Your evidence root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet`

Expected packet manifest:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet/packet_manifest.json`

Closeout path:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_757_web_ads_source_packet_builder_closeout.md`

## Allowed

- Read `~/Docs/Autonomous_business`.
- Read `~/Docs/Web_automation`.
- Use Web_automation code only if all generated outputs are redirected to your Autonomous_business evidence root.
- Write only under your evidence root and your closeout path.
- Inspect command help before running source-related commands.
- Stop `YELLOW` if no safe source-fresh packet can be produced under these constraints.

## Forbidden

- Do not write inside `~/Docs/Web_automation`.
- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate any workbook.
- Do not run scheduler automation or LaunchAgent changes.
- Do not perform browser-login automation.
- Do not export, copy, package, hash, or reveal cookies, credentials, tokens, `.env`, browser profiles, or sessions.
- Do not perform external writes, ad spend, cash movement, price changes, stock changes, or owner publication.
- Do not run the AB adapter or copied/temp replay. That is Agent 758.

## Required Packet Contract

Your packet must make these fields machine-readable where applicable:

- `source_contract_version`
- `packet_root`
- `file_list`
- `packet_sha256_manifest`
- `raw_payload_files`
- `raw_payload_hash_manifest`
- `redaction_manifest`
- `no_secrets_included=true`
- `source_db_sha256`
- `source_db.sha256`
- source schema hash
- source table list
- source row counts
- source columns
- source unique keys
- duplicate source key counts
- capture method and capture timestamp
- business store identity
- access identity
- campaign/status semantics
- spend semantics
- copied/temp adapter metadata placeholder
- validator replay metadata placeholder
- warning cohorts `23` and `252`

Preserve STOREB business identity as `STOREB` even if access is through a Universal login or shared account. Keep access identity separate from business identity.

## Required Validation

Run this from `~/Docs/Autonomous_business` after creating the packet manifest:

```bash
python3 scripts/validate_ads_source_packet_contract.py \
  --manifest ~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet/packet_manifest.json \
  --require-existing-files \
  --strict \
  --json
```

Save the validator JSON/stdout/stderr under your evidence root.

If strict validation fails, stop. Do not run adapter/replay work.

## Closeout Requirements

Write a concise closeout with:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Exact packet manifest path, if created.
- Exact strict validator command and result.
- Source surfaces used.
- Source capture timestamp/as-of semantics.
- Business identity and access identity.
- Row counts, unique keys, duplicate key counts, and warning cohort handling.
- Explicit confirmation that no Web_automation writes, production DB writes, workbook writes, browser-login automation, or credential/session export occurred.
- If not GREEN, the exact missing source/proof requirement.

Only use `Gate: GREEN` if the packet strictly validates and all hard stoplines are clear.
