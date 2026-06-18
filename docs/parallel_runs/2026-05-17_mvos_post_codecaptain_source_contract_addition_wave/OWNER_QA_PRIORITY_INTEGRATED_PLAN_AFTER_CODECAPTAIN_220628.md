# Owner-QA Priority Integrated Plan After CodeCaptain 22:06

Created: `2026-05-17`

Context:

- CodeCaptain answer: `~/Docs/Oracle/Autonomous_business/2026-05-17/213126_TASK-000_mvos-post-codecaptain-source-contract-yellow/Answer/Code Captain - Branch_17.05.2026_22_06_28.md`
- Agent874 packet: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/AGENT874_SYNTHESIS_AND_PROOF.md`
- Agent874 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/agent874_synthesis_copied_temp_proof_closeout.md`

## Authority Order

Use this order when instructions conflict:

1. Repo safety rules and explicit no-production-mutation boundaries.
2. Human owner Q&A in the current orchestrator chat, recorded below.
3. CodeCaptain 22:06 answer where it does not conflict with the owner Q&A.
4. Agent874 source-contract evidence and validator matrices.

This plan does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes beyond approved read-only fetching, ad-platform writes, bank/cash movement, supplier payment, PO commitment, stock changes, price changes, owner publication/send, or production apply.

## Human Owner Q&A Decisions

These decisions supersede conflicting parts of the CodeCaptain 22:06 answer:

| Topic | Owner decision | Effect |
|---|---|---|
| STOREB Kaspi Marketing access | STOREB should be fetched through `UNIVERSAL` login/switcher. | Next ads lane must use `UNIVERSAL_SWITCHER_FOR_STOREB` as the intended read-only route. |
| Meta/Facebook | Fetch May 13-17 Meta evidence. | Do not rely on `META_FACEBOOK_OUT_OF_CURRENT_MVOS_SCOPE_NO_META_PUBLICATION_CLAIMS` as the main route unless fetch fails and owner/CodeCaptain later accepts fallback. |
| Five cancellation rows | Accept API `KASPI_DELIVERY / CANCELLING` rows as copied-temp non-delivered exposure; human may search manually tomorrow. | `API_CANCELLING_NON_DELIVERED_EXPOSURE_FOR_COPIED_TEMP_ONLY_NO_WEBUI_STATUS_CHANGE_AT` is owner-approved for copied-temp planning, but manual WebUI upgrade remains possible. |
| Cancelled/returned archive day-complete rows | Exclude `CANCELLED/ARCHIVE` and `RETURNED/ARCHIVE` from size-complete requirements. | Day-complete validator-contract lane may implement this rule in copied-temp/code-contract form. |
| Blank SKU / `nan` offer rows | Treat blank SKU / `nan` offer rows as missing-line-item evidence, not employee size-entry failure. | Day-complete validator-contract lane may classify these separately from true size-entry incompleteness. |
| Ambiguous row `861147900` | Manually classify from offer text: `Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48`. | The row should be handled as manually classified from offer text, not left as generic unknown. |

## Integrated Diagnosis

CodeCaptain accepted Agent874 as a valid narrowed YELLOW planning anchor and recommended creating a central source-contract registry plus retained-blocker board before the next proof.

That recommendation remains correct, but the owner Q&A upgrades several blockers from open questions into execution inputs:

- Ads is no longer a passive retained blocker. It needs a read-only current refresh lane using `UNIVERSAL` login/switcher for STOREB and May 13-17 Meta/Facebook fetch.
- Lifecycle cancellation is no longer waiting only for CodeCaptain. The copied-temp API exposure contract is owner-approved, while exact WebUI rows may still be supplied manually later.
- Day-complete is no longer only a retained blocker. The owner approved concrete eligibility/classification rules that can be encoded as validator-contract work.

## Most Efficient Next Sequence

### Phase 1: Source Contract Registry And Owner-QA Overlay

Create the contract registry CodeCaptain requested, but seed it with the owner-QA decisions above.

Primary artifacts:

- `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
- `docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
- evidence folder: `exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent875_contract_registry/`

Expected gate:

- `GREEN` if registry is complete and non-authorizing.
- `YELLOW` only if schema/validator wiring must wait.

### Phase 2: Parallel Repair Lanes

Run these in parallel after the registry is created.

#### Lane A: Ads Current Source Refresh

Goal:

- Produce current STOREB+ACMEWEAR Kaspi Marketing DirectAPI evidence through `2026-05-17`.
- Fetch Meta/Facebook May 13-17 evidence.

Route:

1. Use existing repo/Web_automation read-only API methods.
2. Use `UNIVERSAL` login/switcher for STOREB.
3. If API credential resolution fails, use Chrome Auto Connect or headless Playwright read-only fallback.
4. Write immutable local evidence only.
5. Do not mutate Web_automation, ad platforms, bids, budgets, prices, stock, DB, workbook, or scheduler.

Expected result:

- `src_web_automation_kaspi_marketing_directapi` can move toward copied-temp GREEN if coverage becomes complete.
- `src_facebook_ads_external_ads` can move toward copied-temp GREEN if May 13-17 evidence is fetched.

#### Lane B: Lifecycle Cancellation Contract Materialization

Goal:

- Convert owner-approved copied-temp API exposure contract into a registry-backed copied-temp overlay candidate.

Contract:

`API_CANCELLING_NON_DELIVERED_EXPOSURE_FOR_COPIED_TEMP_ONLY_NO_WEBUI_STATUS_CHANGE_AT`

Rules:

- Do not create WebUI `status_change_at`.
- Do not mark as `WEBUI_CANCELLED`.
- Do not add active stock back while `returnedToWarehouse=false`.
- Do not recognize delivered cash-in or sales revenue.
- Keep manual WebUI search as an optional later upgrade path.

Expected result:

- The five cancellation rows can stop blocking copied-temp YELLOW board proof.
- They do not become production lifecycle truth.

#### Lane C: Day-Complete Validator Contract And Backfill

Goal:

- Implement or prove the owner-approved day-complete rules in copied-temp/code-contract form.

Owner-approved rules:

- Exclude `CANCELLED/ARCHIVE` and `RETURNED/ARCHIVE` from size-complete requirements.
- Classify blank SKU / `nan` offer rows as missing-line-item exceptions, not employee size-entry failures.
- Manually classify `861147900` from offer text `Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48`.

Expected result:

- Re-run `validate_day_complete.py --cutoff-date 2026-05-17` on copied-temp/code-contract path.
- If it passes, PO dashboard can be rerun or scoped with fewer blockers.
- If it still fails, retained blockers become much smaller and more actionable.

#### Lane D: Status-Ledger Provenance Materialization

Goal:

- Implement CodeCaptain's useful recommendation: import-existing runs may carry requested `--since/--until` into manifests if source file hashes are recorded and values are emitted by the wrapper, not hand-edited.

Scope:

`MVOS_STATUS_LEDGER_SCOPE_STOREB_ACMEWEAR_UNIVERSAL_FOR_COPIED_TEMP_ONLY`

Expected result:

- Scoped validator should move from `gap_count=3` to pass if manifest windows are correctly materialized.
- `11KZ` and `MELVIS` remain disclosed omitted stores for copied-temp proof unless same-window files are supplied.

### Phase 3: Deliberately YELLOW Board Proof

Run only after Phases 1-2 produce closeouts.

Label:

`MVOS_COPIED_TEMP_BOARD_PROOF_YELLOW_RETAINED_BLOCKERS_VISIBLE`

Purpose:

- Prove the accepted contracts can be materialized on a copied DB.
- Keep unresolved blockers visible.
- Avoid false GREEN.

This proof may become copied-temp GREEN only if the repair lanes genuinely satisfy the validators without hiding retained blockers.

### Phase 4: Production-Preflight Prep

Do not start production-preflight prep until copied-temp proof posture is stable.

Production preflight still requires:

- fresh boundary;
- backup/rollback;
- accepted contracts;
- validator replay;
- exact expected deltas;
- explicit owner authorization.

## Updated Priority Ranking

1. Create source-contract registry with owner-QA overlay.
2. Fetch ads truth using `UNIVERSAL` login/switcher for STOREB and fetch Meta May 13-17.
3. Implement lifecycle copied-temp API exposure contract.
4. Implement day-complete validator contract/backfill using owner-approved rules.
5. Implement status-ledger window provenance emission for scoped stores.
6. Run deliberately YELLOW copied-temp board proof.
7. Ask CodeCaptain only for remaining disputed validator/contract boundaries after these owner-approved fixes are attempted.

## Why This Is Faster Than Waiting

CodeCaptain's answer was written before the owner Q&A. The answer correctly identified the contract architecture, but it treated several routes as unresolved. The owner Q&A resolves enough of those routes to run targeted implementation now.

The efficient strategy is not to wait for another broad CodeCaptain answer. It is to execute the owner-approved source/contract repair lanes, then send CodeCaptain a smaller, sharper packet if any validator still disagrees.

## Stoplines

Stop and report if any lane would require:

- production DB write;
- workbook write;
- scheduler/LaunchAgent/cron mutation;
- source-pointer write;
- Web_automation mutation;
- Kaspi/API/WebUI write beyond read-only fetching;
- ad-platform write;
- cash movement;
- supplier payment;
- PO commitment;
- stock or price change;
- owner publication;
- production apply;
- treating missing ads spend as zero;
- generating WebUI `status_change_at` from API fields;
- hiding day-complete or PO failures;
- labeling a retained-blocker board proof as GREEN.
