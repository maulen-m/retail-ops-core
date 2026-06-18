# May 18 MVOS Retained-Blocker Repair Wave Plan

Created: `2026-05-18`

## Purpose

Implement CodeCaptain's `2026-05-18 09:08` recommendation after Agent880's `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

This wave repairs or preserves the retained blockers without false source substitution:

1. STOREB ads product-code mappings.
2. C3 copied-temp source-freshness bridge.
3. Two day-complete rows.
4. PO Nike-shirt invariant.
5. Status-ledger scoped versus five-store proof.
6. Successor copied-temp board proof.

## Authority

Authority order:

1. Repo safety rules and protected-surface stoplines.
2. Human owner clarifications recorded in `docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`.
3. Human approval in the May 18 orchestrator chat.
4. CodeCaptain `2026-05-18 09:08` answer.
5. Agent880 `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.
6. May 17 owner-QA source-contract registry.

Approved:

- read-only analysis;
- copied-temp-only materialization/proofs;
- repo docs/tests/validator edits needed for approved copied-temp contract behavior;
- local evidence generation;
- STOREB ads read-only discovery through `UNIVERSAL` login/switcher;
- read-only Chrome/Computer/Playwright fallback for STOREB ads discovery if repo/API methods are insufficient.

Not authorized:

- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation mutation;
- Kaspi/API/WebUI writes beyond read-only fetching;
- ad-platform writes;
- bid or budget changes;
- bank/cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication/send;
- external writes;
- production apply.

## Post-CodeCaptain Owner Clarifications

The following owner decisions are authoritative for the retained-blocker repair sequence, copied-temp proof only:

- `11120372b` (`ALPIKA черный`) and `11942309b` (`PRO COMBAT черный`) are Line52 product-group ads and may map to `CL_OC_MEN_LINE52_BLACK`.
- Size `S` is orderable for `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK`.
- Scoped `STOREB`/`ACMEWEAR`/`UNIVERSAL` status-ledger proof is officially enough for this current copied-temp MVOS proof, while `11KZ` and `MELVIS` must remain disclosed as omitted.
- The C3 source-freshness bridge may use only already accepted packets/contracts; unaccepted sources remain visible blockers.

## Prior Controlling Evidence

CodeCaptain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-17/231037_TASK-000_mvos-owner-qa-board-proof-codecaptain-final/ANSWER/Code Captain_18.05.2026_09_08_18.md`

Agent880 closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent880_synthesis_copied_temp_board_proof_closeout.md`

Agent880 evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_owner_qa_repair_wave/20260517_2223/agent880_synthesis_copied_temp_board_proof`

May 17 owner-QA registry:

`~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`

## Root Parallel Lanes

### Agent881: STOREB Ads Mapping Source Decision

Scope:

- Resolve or retain the nine blocked STOREB product-code mappings from Agent880.
- Build `STOREB_PRODUCT_CODE_MAPPING_SOURCE_DECISIONS.csv`.
- Build `STOREB_UNMAPPED_POSITIVE_SPEND_RETAINED_BLOCKERS.csv`.
- Read `Autonomous_business`, `Web_automation`, and existing source evidence.
- Use existing API/repo data first.
- If needed, use read-only Chrome/Computer/Playwright with `UNIVERSAL` login/switcher to inspect STOREB Kaspi Marketing.

Stoplines:

- Do not mutate Web_automation.
- Do not write ad platform state.
- Do not treat missing/unmapped spend as zero.
- Do not force fuzzy mappings for green.

### Agent882: C3 Source-Freshness Bridge

Scope:

- This is the only root write-capable repo lane.
- Implement copied-temp-only source-freshness bridge docs/tests/materialization support as needed.
- Produce `COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_CONTRACT.md`.
- Produce `SOURCE_FRESHNESS_BRIDGE_MATERIALIZATION_SUMMARY.json`.
- Prove bridge rows only inside copied DB/evidence.

Stoplines:

- Do not update production `db/app.db`.
- Do not create production source-freshness authority.
- Do not clear owner-publication gates unless validators genuinely pass on accepted copied-temp proof.

### Agent883: Day-Complete Two-Row Repair

Scope:

- Source-discover the two remaining day-complete rows:
  - `844362551 / ACMEWEAR / CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL`
  - `861137901 / UNIVERSAL / CL_NEW-CLO_KIDS_KID-31_BLACK`
- Build `DAY_COMPLETE_FINAL_TWO_ROWS_SIZE_EVIDENCE.csv`.
- Build `DAY_COMPLETE_RERUN_AFTER_FINAL_TWO_ROWS.json` if source evidence is sufficient for copied-temp rerun.

Stoplines:

- Do not invent sizes.
- Do not hide unresolved rows behind exclusions.
- If source evidence is insufficient, keep rows as owner/source-decision required.

### Agent884: Status-Ledger Scope / Five-Store Proof

Scope:

- Decide whether the next proof should remain scoped `STOREB/ACMEWEAR/UNIVERSAL` or attempt full five-store proof.
- If source evidence exists or can be fetched read-only, gather same-window `11KZ` and `MELVIS` WebUI Archive evidence.
- Produce `STATUS_LEDGER_SCOPE_DISCLOSURE.md`.
- If full five-store evidence is available, run copied-temp/full-ledger validation evidence.

Stoplines:

- Do not claim five-store green without same-window evidence.
- Do not synthesize status-change chronology.

## Dependent Lanes

### Agent885: PO Nike-Shirt Invariant Analysis

Launch after Agent883 closes out.

Scope:

- Analyze `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK` after consuming the day-complete lane.
- Produce `PO_NIKE_SHIRT_INVARIANT_ANALYSIS_AFTER_DAY_COMPLETE.json`.
- Decide whether the `0.4274` delta is source mismatch, rounding/allocation artifact, or retained blocker.

Stoplines:

- Do not infer PO green from day-complete repair alone.
- Do not commit PO or mutate PO dashboard production truth.

### Agent886: Successor Copied-Temp Board Proof

Launch after Agents881-885 close out and the orchestrator reviews their artifacts.

Scope:

- Copy the current production DB into assigned evidence only.
- Apply copied-temp-only accepted repair artifacts.
- Rerun validator matrix.
- Emit successor board matrix.
- Use `COPIED_TEMP_GREEN_PROOF_READY` only if all required validators genuinely pass and no retained blocker remains.
- Otherwise use `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` with blockers visible.

Stoplines:

- No production DB apply.
- No workbook/scheduler/source-pointer/external write.
- No false green.

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS`

## Success Criteria

- Agents881-884 close out with standalone `Gate:` lines and evidence.
- Agent885 closes out after Agent883.
- Agent886 produces a successor copied-temp board proof.
- `scripts/lint_docs.sh` passes.
- `scripts/check_no_db_tracked.sh` passes.
- Protected production surfaces remain unmodified.
- The final state is either true copied-temp green or an honest blocker-visible yellow.
