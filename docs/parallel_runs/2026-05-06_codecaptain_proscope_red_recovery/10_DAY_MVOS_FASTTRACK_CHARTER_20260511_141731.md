# 10-Day MVOS Fast-Track Charter

Generated at: `2026-05-11T14:17:31+0500`

Status: `MVOS_FASTTRACK_ACTIVE_REVIEW_ONLY`

Owner fast-track token: `OWNER_FASTTRACK_APPROVED_NO_ARTIFICIAL_WAIT`

## Mission

Make Autonomous Business survival-useful as fast as safely possible by producing one daily owner/operator operating packet before attempting full automation.

The 10-day schedule is an upper-bound checkpoint ladder. If review-only phases can be completed earlier, they should be completed earlier. Do not wait for calendar estimates after gates are green.

## Survival Outputs

The MVOS daily operating packet must answer:

- cash risk: what is safe to monitor, and what cash actions are blocked;
- stock/order risk: what fulfillment or sales risks need manual attention;
- ads status: ACMEWEAR copied/temp freshness, STOREB source gap, and blocked ads-dependent decisions;
- source freshness: trusted, stale, or gap by source area;
- exceptions: visible `23` and `252` warning cohorts;
- allowed decisions: review-only monitoring and manual prioritization;
- blocked decisions: owner publication, scheduler, production writes, external writes, cash movement, PO commitment, ad spend, price changes, and stock changes.

## Current Accepted Evidence

- Cash Risk Daily copied-DB proof is accepted for review-only use.
- Operator Phase `5.5` acceptance is recorded for owner-publication readiness delta sequencing.
- Agent757 source packet is strict-validated for ACMEWEAR.
- Agent758 copied/temp replay is accepted by CodeCaptain for the next review-only sequence.
- Agent758 clears stale ads only as `ADS_SOURCE_STALE_CLEARED_FOR_ACMEWEAR_COPIED_TEMP_REPLAY_ONLY`.
- STOREB remains `STOREB_ADS_SOURCE_GAP_VISIBLE_NOT_ZERO_SPEND`.

## Fast-Track Phase Ladder

Phase A: MVOS charter and integration record.

Status: complete by this record.

Phase B: Daily Survival Brief v1.

Target: immediately after read-only analyst reports are ready, not a calendar day later.

Phase C: operating rehearsal.

Target: run as soon as Daily Survival Brief v1 is reproducible. If three distinct daily source windows are not yet available, run repeated validate-only dry rehearsal and mark date-dependence explicitly.

Phase D: owner-publication readiness delta.

Target: as soon as the brief wording is stable and warnings/blocked decisions remain visible.

Phase E: scheduler design-only.

Target: can run in parallel as read-only/design-only work; no install, enablement, LaunchAgent mutation, or production writes.

Phase F: survival review.

Target: immediately after enough evidence exists to decide whether to continue manual MVOS, prepare an owner monitoring packet, or request a separate scheduler dry-run review.

## Parallelization

Unlimited read-only agents may run in parallel when they publish separate handoff reports and do not mutate repo state.

Serialized or blocked surfaces:

- `.claude/*` and active status pointers: one writer/scribe only;
- `db/app.db`: blocked in this phase;
- `excel_ui/SALES_KSP_CRM_V3.xlsx`: blocked in this phase;
- scheduler/LaunchAgent files: blocked in this phase;
- Web_automation and external systems: blocked in this phase.

## Acceptance Criteria

MVOS fast-track is active when:

- the CodeCaptain answers are recorded with exact decision tokens;
- the owner fast-track decision is recorded;
- the active stopline points to Daily Survival Brief v1;
- starter prompts exist for parallel read-only analysis and one serialized writer;
- validation confirms JSON is parseable and docs have no diff whitespace issues.

Daily Survival Brief v1 is acceptable when:

- it uses the three exact ads labels from the integration record;
- it keeps `23` and `252` visible;
- it contains explicit allowed/blocked decisions;
- it does not claim owner publication, production, scheduler, cash, PO, ad-spend, price, or stock authority.
