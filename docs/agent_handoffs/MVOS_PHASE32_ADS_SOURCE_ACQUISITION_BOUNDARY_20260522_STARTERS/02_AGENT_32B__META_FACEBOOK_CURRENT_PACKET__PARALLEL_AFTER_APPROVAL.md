# Agent 32B - Meta/Facebook Current Packet

Gate: `PENDING`

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. this prompt

## Hard Gate

Do not perform live Meta/Facebook reads until the exact Phase32 owner approval phrase is present in the orchestrator chat or a CodeCaptain answer explicitly authorizes the route.

If approval is missing, write a `YELLOW_APPROVAL_MISSING` closeout and stop.

## Task

Acquire or prepare a current accepted Meta/Facebook source packet for:

- `source_id=src_facebook_ads_external_ads`
- current requested window through `2026-05-22`
- accepted packet filename `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json`

Allowed only after the hard gate:

- read-only Meta/Facebook source fetches;
- generated local Phase32 evidence/run artifacts only in the approved output boundary;
- copied redacted/hash evidence under `~/Docs/Autonomous_business/exports/validation/mvos_phase32_ads_source_acquisition_boundary`;
- closeout writing.

Forbidden:

- platform writes;
- campaign, ad set, ad, bid, budget, status, URL, creative, or spend changes;
- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- secret/cookie/storage-state copying;
- owner publication.

## Success Criteria

`GREEN` only if the packet meets every Meta/Facebook requirement in the Phase32 boundary document and protected surfaces remain unchanged.

If any positive spend appears, do not silently clear ads truth. Stop `YELLOW` unless the Phase32 approval or CodeCaptain answer explicitly allows source freshness to clear while spend ingestion remains separate.

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/agent32b_meta_facebook_current_packet_closeout.md`
