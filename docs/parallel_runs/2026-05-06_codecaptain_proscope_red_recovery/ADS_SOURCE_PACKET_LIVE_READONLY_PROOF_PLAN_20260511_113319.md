# Ads Source Packet Live-Readonly Proof Plan

Status: AGENT757_LAUNCHED_MONITOR_ONLY
Created: 2026-05-11 11:33:19 +0500
Owner boundary: Autonomous_business proof lane, with read-only Web_automation source access only.

## Imported Decision

CodeCaptain answer:
`~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`

Accepted gate:
`GREEN_ACCEPT_ADS_SOURCE_PACKET_CONTENT_CONTRACT_FOR_LIVE_READONLY_PROOF`

Execution strategy:
`proceed_to_live_readonly_proof`

This plan supersedes the prior "waiting for source-packet content re-review" status. It authorizes only the next bounded proof lane. It does not authorize production database writes, workbook writes, scheduler automation, LaunchAgent changes, owner publication, owner approval requests, Web_automation repo writes, browser-login automation, credential/session export, external writes, ad spend, cash movement, PO commitment, price changes, or stock changes.

## Goal

Produce one auditable proof that the ads source freshness blocker can be resolved or reclassified without mutating production truth:

1. Build an immutable ads source packet from read-only Web_automation source surfaces.
2. Validate the packet with the strict source-packet contract validator.
3. If and only if the packet is valid, adapt it into copied/temp Autonomous_business proof storage.
4. Replay `ads_sidecar_readiness` and `ads_offer_universe_coverage` against the copied/temp proof boundary.
5. Close with one of these outcomes:
   - `ADS_SOURCE_STALE` clears by source-fresh packet.
   - `ADS_SOURCE_STALE` remains visible with exact source reason.
   - The blocker is reclassified to a machine-readable source/coverage gap.

## Evidence Roots

Run root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319`

Launch record:
`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_AGENT757_LAUNCH_20260511_113748.md`

Tmux manifest:
`~/Docs/Autonomous_business/runs/tmux_orchestration/ads_source_packet_live_readonly_proof_20260511_113319/orchestration_manifest.json`

Agent 757 packet root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet`

Expected packet manifest:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet/packet_manifest.json`

Agent 758 replay root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent758_replay`

Expected copied DB:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent758_replay/app_copy.sqlite`

## Agent Sequence

Agent 757: Web Ads Source Packet Builder

Assignment: build and strict-validate the immutable ads source packet from reviewed Web_automation source surfaces. It may read Web_automation code/data and may write only under its assigned evidence root plus its closeout file. It must not write inside `~/Docs/Web_automation`. If a safe source-fresh packet cannot be produced without forbidden access or forbidden writes, it must stop `Gate: YELLOW` with the exact missing source requirement.

Agent 758: AB Copied-Temp Adapter Replay

Assignment: only after Agent 757 closes `Gate: GREEN`, copy the AB production DB into the evidence root, adapt the validated source packet into copied/temp proof storage, and replay the ads validators against the copied/temp boundary. If Agent 757 is not GREEN, Agent 758 must not run.

## Required Agent 757 Packet Fields

The packet must make these fields machine-readable where applicable:

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

Required validation command:

```bash
python3 scripts/validate_ads_source_packet_contract.py \
  --manifest ~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent757_packet/packet_manifest.json \
  --require-existing-files \
  --strict \
  --json
```

Agent 757 must not run the adapter. Packet validation failure stops the lane before Agent 758.

## Required Agent 758 Replay

Agent 758 must preserve production by using a copied/temp DB only:

- Copy `~/Docs/Autonomous_business/db/app.db` to the Agent 758 evidence root.
- Record production DB SHA before copy and copied DB SHA after copy.
- Adapt only from the validated packet manifest into the copied/temp DB or copied/temp sidecar.
- Run replay validators against the copied/temp boundary only.
- Preserve validator JSON/stdout/stderr under the replay root.
- Keep warning cohorts `23` and `252` visible; do not hide or smooth them.

## Hard Stoplines

Stop `RED` or `YELLOW`, as appropriate, if any of these appear:

- Secrets, cookies, sessions, tokens, credentials, `.env`, or browser profile artifacts are included or exported.
- Packet paths escape the evidence root or use path traversal.
- SHA manifests are incomplete or contradict the files they describe.
- Raw payloads are missing, unhashable, or not represented by the manifest.
- Redaction metadata contradicts `no_secrets_included=true`.
- Source DB SHA mismatches the declared source DB file.
- Duplicate source keys make the packet ambiguous.
- Business identity and access identity conflict.
- Missing spend/campaign rows are silently treated as zero.
- Stale source rows are rewritten as fresh.
- Agent 758 falls back to production DB mutation.
- Agent 758 writes outside the evidence root.
- Warning cohorts `23` or `252` are hidden or collapsed.

## Current Launch Rule

Launch only Agent 757 now.

Do not launch Agent 758 until the Agent 757 closeout contains a standalone:

`Gate: GREEN`

and the strict validator output is present in the Agent 757 evidence root.
