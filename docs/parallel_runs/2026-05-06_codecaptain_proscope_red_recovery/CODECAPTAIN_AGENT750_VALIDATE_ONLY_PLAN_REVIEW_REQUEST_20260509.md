# CodeCaptain Review Request - Agent750 Option C Validate-Only Plan

Phase: Current dec77 post-reanchor validate-only planning review
Focus: decide whether the team may launch the validate-only implementation wave, not production automation

Refreshed note: this request supersedes any earlier wording that implied a `YELLOW` or generic non-RED CodeCaptain answer could launch Agent751/752/753. Launch authority requires the exact GREEN decision token `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`; `YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE` means fix first, and `RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE` means stop.

## Request

Please review the attached Agent750 plan and evidence pack as the highest-authority current planning surface for Option C validate-only work.

We need your decision on whether the orchestrator can safely launch the next validate-only wave:

- Agent751: sole write-capable tests-first implementation agent for the validate-only runner contract.
- Agent752: read-only Cash Risk Daily owner-output surface analyst.
- Agent753: read-only source freshness and exception queue analyst.

This review must not approve production scheduler automation, workbook writes, production DB writes, external-system writes, owner decision publication, owner approval requests, old Agent54 phrase reuse, or Agent64 activation.

## Current Boundary

Use this boundary as current:

- Production DB: `~/Docs/Autonomous_business/db/app.db`
- Current DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Protected workbook: `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- Protected workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Current release anchor: `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/`

## Authority Chain

- Agent746 forensics found the old Agent742 DB SHA boundary stale and identified current `dec77...ee64` as the live production boundary.
- Agent747 created the current `dec77` release anchor and closed `YELLOW`.
- Agent748 independently confirmed the current `dec77` boundary and closed `YELLOW`.
- Agent749 hardened the strict daily preflight proof-window lock and closed `GREEN`.
- Agent750 drafted the current-boundary Option C validate-only plan and starter prompts 751/752/753 and closed `GREEN`.

Important: Agent743/744 and stale Agent745 must not be used as current authority. They were rooted in the superseded Agent742 `9c51...ee53` boundary.

## What To Evaluate

Please evaluate:

1. Whether Agent750 correctly supersedes stale Agent742/743/744/745 authority with the current Agent746/747/748/749 chain.
2. Whether Agent750's plan is safe to implement as validate-only work.
3. Whether Agent751/752/753 starter prompts are correctly scoped and dependency-gated.
4. Whether the proof-window lock behavior is sufficient as a prerequisite for validate-only implementation work.
5. Whether `Cash Risk Daily` is the right first owner-output surface.
6. Whether the trust banner schema is strong enough to prevent false-green owner decisions.
7. Whether source freshness, warning cohorts, leakage, and cash preservation remain visible and fail-closed.
8. Whether any additional tests or validators are required before launching Agent751.
9. Whether a CodeCaptain review should be required again after Agents751/752/753 and before any scheduler lane.
10. Any root risks we may still be missing.

## Decision Needed

Return one of:

- `GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE`
- `YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE`
- `RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE`

If not GREEN, list the smallest required fixes in priority order.

## Non-Negotiable Boundaries

Even if this review is GREEN:

- no production scheduler install or enablement;
- no LaunchAgent mutation;
- no production DB write;
- no workbook write;
- no external-system write;
- no Kaspi/API/ads/Google/bank/Web_automation/browser write;
- no owner approval request;
- no production owner decision publication;
- no old Agent54 phrase reuse;
- no Agent64 activation.

## Preferred Answer Format

Start with:

```text
Phase: <phase>
Focus: <focus>
Gate: <GREEN/YELLOW/RED decision token>
```

Then provide:

1. Recommendation box: Problem -> Impact -> Proposed fix -> Effort -> Priority.
2. Evidence you trust.
3. Evidence you do not trust or consider insufficient.
4. Capital-risk analysis.
5. Required fixes, if any.
6. Exact next implementation sequence.
7. Stoplines.
8. Concrete next actions for the orchestrator.
