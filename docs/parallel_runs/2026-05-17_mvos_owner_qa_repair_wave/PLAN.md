# MVOS Owner-QA Repair Wave Plan

Created: `2026-05-17`

## Purpose

Implement the owner-QA-priority MVOS repair wave after CodeCaptain's `2026-05-17 22:06` answer and the owner's six clarifications in the orchestrator chat.

This wave converts the narrowed Agent874 YELLOW planning anchor into a registry-backed repair pass, then runs a copied-temp MVOS board proof. The board proof may be `GREEN` only if validators genuinely pass; otherwise it must stay `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` with blockers visible.

## Authority

Authority order:

1. Repo safety rules and protected-surface stoplines.
2. Owner Q&A decisions recorded in `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`.
3. CodeCaptain `2026-05-17 22:06` answer where it does not conflict with owner Q&A.
4. Agent874 evidence and validator matrices.

Not authorized:

- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation mutation;
- Kaspi/API/WebUI writes beyond read-only fetching;
- ad-platform writes, bid changes, or budget changes;
- bank/cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication/send;
- external writes;
- production apply.

## Completed Phase

Agent875 contract registry is complete.

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent875_contract_registry_closeout.md`

Artifacts:

- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`

## Root Parallel Lanes

### Agent876: Ads Current Source Refresh

Scope:

- Read-only source refresh for STOREB Kaspi Marketing via `UNIVERSAL` login/switcher.
- Read-only source refresh for ACMEWEAR Kaspi Marketing.
- Read-only Meta/Facebook May 13-17 evidence.
- Existing API methods first; Chrome Auto Connect or headless Playwright fallback only if needed and read-only.

Writes:

- Out-of-repo handoff/evidence folder only.

Stoplines:

- Do not mutate Web_automation.
- Do not write ad-platform state.
- Do not infer missing spend as zero.

### Agent877: Lifecycle API Exposure Materialization

Scope:

- Build copied-temp-only evidence for the five `KASPI_DELIVERY / CANCELLING` rows using `API_CANCELLING_NON_DELIVERED_EXPOSURE_FOR_COPIED_TEMP_ONLY_NO_WEBUI_STATUS_CHANGE_AT`.
- Prove no WebUI `status_change_at` is synthesized.
- Keep manual WebUI upgrade path separate.

Writes:

- Out-of-repo handoff/evidence folder only.

Stoplines:

- Do not mark API exposure as WebUI cancelled.
- Do not recognize delivered cash-in or sales revenue.
- Do not add active stock back while `returnedToWarehouse=false`.

### Agent878: Day-Complete And Status-Ledger Contract Repair

Scope:

- This is the only root write-capable repo lane.
- Implement docs/tests/validator repair for owner-approved day-complete behavior.
- Implement docs/tests/validator or wrapper repair for status-ledger manifest window provenance if required.

Owner-approved day-complete behavior:

- `CANCELLED/ARCHIVE` and `RETURNED/ARCHIVE` rows may be excluded from size-complete requirements.
- Blank SKU / `nan` offer rows may be treated as missing-line-item exceptions, not employee size-entry failures.
- Order `861147900` may be manually classified from offer text `Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48`.

Writes:

- Focused repo docs/tests/validator edits only.
- Assigned repo evidence folder and out-of-repo closeout.

Stoplines:

- Do not write production DB.
- Do not write workbook.
- Do not hide true employee size-entry failures.
- Do not hand-edit status-ledger window provenance.

### Agent879: Source-Freshness And Retained-Blocker Analyst

Scope:

- Read-only analysis of source-freshness rows, policy gates, retained blocker board inputs, and exact validator command matrix needed for Agent880.
- Confirm which blockers should remain visible after Agents876-878.

Writes:

- Out-of-repo handoff/evidence folder only.

Stoplines:

- Do not mutate repo files, DB, workbook, scheduler, source pointers, Web_automation, or external systems.

## Dependent Lane

### Agent880: Synthesis Copied-Temp MVOS Board Proof

Launch only after Agents876-879 close out and the orchestrator reviews the actual closeouts.

Scope:

- Consume Agent875-879 outputs.
- Capture protected boundary.
- Copy DB into assigned evidence only.
- Run copied-temp materialization/proof commands that are safe under the accepted contracts.
- Emit board result as `GREEN` only if validators genuinely pass.
- Otherwise emit `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` with blockers visible.

Stoplines:

- No production DB apply.
- No workbook/scheduler/external write.
- No false GREEN.

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_QA_REPAIR_WAVE_20260517_STARTERS`

## Success Criteria

- Agent875 registry remains GREEN.
- Agents876-879 close out with evidence and standalone gate lines.
- Agent880 produces copied-temp board proof with honest gate.
- `scripts/lint_docs.sh` passes.
- `scripts/check_no_db_tracked.sh` passes.
- Protected production surfaces remain unmodified unless a later exact owner approval phrase authorizes them.
