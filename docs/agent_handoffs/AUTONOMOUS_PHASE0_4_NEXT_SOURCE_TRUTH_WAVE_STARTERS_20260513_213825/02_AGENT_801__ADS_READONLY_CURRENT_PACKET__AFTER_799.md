# Agent801 - Ads Read-Only Current Packet Discovery

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_4_next_source_truth_wave/agent801_ads_readonly_current_packet_20260513_213825_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ORCHESTRATOR_REVIEW_AGENT799_RED_ACCEPTANCE_AND_PHASE0_4_LAUNCH_20260513_213825.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_PLAN_20260513_213825.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_HANDOFF_20260513_213825.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent799_synthesis_20260513_192243_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent795_ads_source_packet_20260513_192243_closeout.md`
9. `~/Docs/Autonomous_business/docs/agent_handoffs/AUTONOMOUS_PHASE0_4_NEXT_SOURCE_TRUTH_WAVE_STARTERS_20260513_213825/02_AGENT_801__ADS_READONLY_CURRENT_PACKET__AFTER_799.md`

## Mission

Discover whether a current, no-secret, immutable ads source packet can be assembled from already-existing local evidence for:

- ACMEWEAR Kaspi Marketing through `2026-05-13`
- STOREB Kaspi Marketing through `2026-05-13`
- ACMEWEAR Meta/Facebook through `2026-05-13` if local non-secret evidence exists

This is read-only discovery and packet assembly only.

## Scope

Allowed:

- Read AB repo files.
- Read `~/Docs/Web_automation` docs, non-secret run artifacts, and local SQLite databases using read-only commands.
- Write only under:
  `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_4_next_source_truth_wave/20260513_213825/agent801_ads_readonly_current_packet/`
- Copy non-secret source extracts/manifests into that evidence root if they are already local and do not contain secrets.
- Run AB validators in read-only/copy-only mode with all outputs under the evidence root.
- Write the assigned closeout.

Forbidden:

- Browser login.
- Reading, copying, exporting, or printing `.env`, cookies, storage state, browser profiles, credentials, session tokens, or secret material.
- Web_automation writes.
- Live fetches or external reads that create new provider/API traffic unless a later explicit approval exists.
- Production `db/app.db` mutation.
- Protected workbook mutation.
- Scheduler/LaunchAgent mutation.
- Source-pointer replacement.
- Owner publication.
- Ad-platform writes, cash movement, PO commitment, supplier contact, price change, stock change, or owner-decision application.

## Required Work

1. Write a READCHECK file listing every bootstrap file read.
2. Recheck the accepted Agent799 boundary as read-only context:
   - DB SHA `40d21f643caefc38270427096ee615fe0667f7d90b628acf5da56d080ad783d1`
   - workbook SHA `e7ff6fd8da8938b3247343a58e1257c102ac1d62077f68f33ad7a5b8a45ec870`
3. Inventory existing AB ads evidence and Web_automation local non-secret evidence for ACMEWEAR/STOREB through `2026-05-13`.
4. Do not inspect or copy secret-bearing files. Record skipped secret paths by category only, not contents.
5. If a packet can be assembled from existing local non-secret files, build a packet folder under the Agent801 evidence root with:
   - manifest;
   - SHA-256 file list;
   - raw payload hash manifest;
   - source DB SHA if a local DB is used;
   - no-secrets redaction manifest;
   - store identity mapping with STOREB business identity separate from access identity;
   - date window and captured/finished timestamps;
   - gap semantics for missing rows.
6. Run `scripts/validate_ads_source_packet_contract.py --help` and then validate the packet if possible.
7. If current evidence is missing, do not fabricate zeros. Produce an exact missing-source matrix and the smallest explicit approval/command needed for the next live-readonly capture lane.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- `Domain Status: GREEN/YELLOW/RED`;
- exact evidence root;
- exact local sources inspected;
- no-secret statement;
- date/store/campaign coverage matrix;
- STOREB business-vs-access identity statement;
- packet validation result or exact missing-source blocker;
- statement that no browser login, credential/session export, Web_automation write, external write, production DB/workbook/scheduler/source-pointer mutation, ad-platform write, or owner publication occurred.

Gate guidance:

- `GREEN` only if a current no-secret packet exists and validates.
- `YELLOW` if the lane produces a precise missing-source plan without needing forbidden actions.
- `RED` if current packet assembly requires forbidden credential/session/browser/Web_automation/live-fetch behavior or if secret risk cannot be ruled out.
