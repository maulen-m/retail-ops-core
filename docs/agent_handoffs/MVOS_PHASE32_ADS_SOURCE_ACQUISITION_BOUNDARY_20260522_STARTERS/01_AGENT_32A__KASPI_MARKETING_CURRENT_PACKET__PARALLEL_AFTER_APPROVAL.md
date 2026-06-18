# Agent 32A - Kaspi Marketing Current Packet

Gate: `PENDING`

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. this prompt

## Hard Gate

Do not perform live fetches until the exact Phase32 owner approval phrase is present in the orchestrator chat or a CodeCaptain answer explicitly authorizes the route.

If approval is missing, write a `YELLOW_APPROVAL_MISSING` closeout and stop.

## Task

Acquire or prepare a current accepted Kaspi Marketing DirectAPI source packet for:

- `source_id=src_web_automation_kaspi_marketing_directapi`
- `as_of=2026-05-22`
- stores `STOREB` and `ACMEWEAR`

Allowed only after the hard gate:

- read-only Kaspi Marketing fetches;
- generated local Phase32 evidence/run artifacts only in the approved output boundary;
- copied redacted/hash evidence under `~/Docs/Autonomous_business/exports/validation/mvos_phase32_ads_source_acquisition_boundary`;
- closeout writing.

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- code/config edits in Web_automation;
- Kaspi/API/WebUI mutations;
- ad-platform writes;
- ad spend, bid, budget, status, campaign changes;
- secret/cookie/storage-state copying;
- owner publication.

## Success Criteria

`GREEN` only if the packet meets every Kaspi Marketing requirement in the Phase32 boundary document and protected surfaces remain unchanged.

Otherwise write `YELLOW` with exact missing fields, source coverage gaps, no-write proof gaps, or boundary blockers.

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/agent32a_kaspi_marketing_current_packet_closeout.md`
