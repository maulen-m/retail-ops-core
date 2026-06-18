# LINE31 Post-Expert Strict Publish Integration Plan

Created: 2026-06-02

## Source

External expert answer:

`~/Docs/Oracle/Autonomous_business/2026-06-01/211503_TASK-000_line31-progress-full-reevaluation-external-expert/Answer/Strategy_expert_02.06.2026_11_14_17.md`

## Objective

Integrate the 2026-06-02 expert review into the Autonomous_business LINE31 launch-readiness path as a practical, testable, execution-ready contract.

The result must let a future orchestrator move fast without fake green declarations:

- internal planning may remain `GREEN_EXCEPT_CREATIVE` only for non-creative LINE31 prep;
- owner-facing publish status must be `YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA` until final creative, mapping, owner approval evidence, tracking QA, and protected-surface checks pass;
- final Meta publish remains a separate live-write action requiring exact owner approval.

## Current Verified Baseline

As of the pre-handoff review:

- `python3 scripts/report_line31_next_inputs_status.py --json` reports `READY_TO_INGEST_EXPERT_ANSWER`.
- Expert answer file count is `1`.
- Current planning status is `GREEN_EXCEPT_CREATIVE`.
- Strict publish gate is `YELLOW`.
- Ready to publish is `false`.
- Final creative video count is `0`.
- Final thumbnail count is `0`.
- Approval text is not present.

## Non-Negotiable Expert Verdict

The expert answer must be treated as a launch-gating addendum:

- `GREEN_EXCEPT_CREATIVE` is a narrow internal prep label, not a publish-ready label.
- A final asset drop is not enough to publish.
- Strict publish readiness also requires final mapping fields, local SHA evidence, exact owner approval in a separate evidence file, fresh tracking and redirect QA, protected hash recheck, cash/stock gate refresh, and no placeholder URLs.
- Internal Kaspi LINE31 campaigns and seller bonus context stay ON unless a separate exact owner approval phrase authorizes isolation or pause.
- Old candidate/noindex route maps are history/context only; current launch truth must use current live route evidence.

## Phase 0 - Bootstrap And Freeze The Current Meaning

Goal: make the current state unambiguous before changing docs, tests, or validators.

Required actions:

- read `AGENTS.md` and `docs/00_START_HERE.md`;
- read the expert answer file;
- read `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`;
- read `docs/current/LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md`;
- read `docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md`;
- run the current status command;
- record protected `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx` hashes before work.

Pass gate:

- current state is explicitly classified as `GREEN_EXCEPT_CREATIVE` for internal prep and strict `YELLOW` for publish.

Stopline:

- stop `YELLOW` if the expert answer path is missing;
- stop `RED` if protected production surfaces drift during a quiet interval before any local edit.

## Phase 1 - Canonical Repo Integration

Goal: make the expert verdict durable in repo docs.

Required actions:

- update owner-facing wording so future agents do not translate `GREEN_EXCEPT_CREATIVE` into publish-ready;
- add or maintain the strict-publish addendum at `docs/validation/LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md`;
- update `docs/current/LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md` so it no longer says the expert `Answer/` folder is empty;
- keep the existing final creative publish starter as the downstream lane, not the authority for post-expert integration;
- preserve exact future approval phrases without treating them as current authorization.

Pass gate:

- docs state that strict publish is blocked until final creative mapping, exact owner approval evidence, live tracking QA, and protected-surface recheck pass.

Stopline:

- stop `YELLOW` if docs conflict with the expert answer or imply live publish authority.

## Phase 2 - Validator And Test Hardening

Goal: close the expert-identified false-green risks.

Required hardening targets:

- final mapping must reject `REPLACE_WITH` placeholder values;
- local thumbnail evidence must require SHA-256 when a local thumbnail path is used;
- final creative drop must fail closed on zero or multiple videos or thumbnails;
- strict launch readiness must require a fresh tracking/redirect QA artifact before publish;
- preflight packet must surface tracking/redirect QA and owner source freshness;
- status reporter must clearly distinguish expert-answer-ingested, waiting-for-final-creative, waiting-for-approval, and ready-to-publish states.

Expected tests:

- focused LINE31 validator tests prove pending-creative mode can pass while strict mode fails before final assets;
- focused mapping tests prove local thumbnail SHA is required;
- focused readiness or preflight tests prove missing tracking QA keeps strict publish non-green;
- status reporter tests prove expert answer presence is detected and does not imply publish readiness.

Pass gate:

- focused LINE31 tests pass, docs lint passes, and strict readiness still fails as expected before final creative and approval evidence.

Stopline:

- stop `YELLOW` if hardening requires a live deploy or external write;
- stop `RED` if any validator silently writes protected DB/workbook or external systems.

## Phase 3 - Read-Only Current Evidence Refresh

Goal: prove the launch environment is still safe without mutating protected surfaces.

Required commands:

```bash
python3 scripts/report_line31_next_inputs_status.py --json
python3 scripts/build_line31_current_noncreative_gate_matrix.py --json
python3 scripts/validate_line31_owner_objective_source_freshness.py --json
python3 scripts/build_line31_launch_preflight_packet.py --json
python3 scripts/audit_line31_active_goal_completion.py --json
python3 scripts/validate_line31_current_final_creative_drop.py --json
python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative --json
python3 scripts/validate_line31_launch_readiness.py --json
```

Expected state before final creative:

- current drop validation is `NOT_READY`;
- pending-creative readiness is `GREEN_EXCEPT_CREATIVE`;
- strict publish readiness is `YELLOW`;
- no live publish or external mutation occurs.

Pass gate:

- failures match the expected missing-final-creative and missing-owner-approval blockers only, plus any clearly labeled advisory blockers.

Stopline:

- stop `YELLOW` if a LINE31 launch-blocking non-creative gate regresses;
- stop `RED` if protected surface hashes drift without authorization.

## Phase 4 - Orchestrator Closeout

Goal: finish with an execution-ready route rather than another abstract report.

Required outputs:

- updated plan/addendum/current docs;
- updated or new focused tests if validators were patched;
- command ledger;
- protected hash ledger;
- retained blocker list;
- next exact starter prompt;
- exact future owner approval phrases.

Closeout gate must be exactly one of:

- `Gate: GREEN_POST_EXPERT_STRICT_PUBLISH_INTEGRATION_READY`
- `Gate: YELLOW`
- `Gate: RED`

`GREEN_POST_EXPERT_STRICT_PUBLISH_INTEGRATION_READY` means the repo is ready for final creative intake and strict validation, not that Meta publish is authorized.

## Phase 5 - Downstream Final Creative And Publish Boundary

This phase is not authorized by this plan. It is listed so the next orchestrator knows where the boundary is.

After the owner provides final creative assets, final URLs, and exact approval evidence, the downstream lane is:

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md`

That downstream lane may only proceed to live Meta publish after strict validation passes and the owner provides the exact LINE31 publish approval phrase.

## Required Future Approval Phrases

These phrases are templates only. They do not authorize action until the owner fills the exact paths, hashes, URLs, IDs, budgets, and explicitly sends the phrase for that live route.

### Final Creative-Ready Declaration

```text
I declare that the final LINE31 countrywide Meta creative package is complete and ready for launch-readiness validation. The current drop folder must contain exactly one final video and exactly one final thumbnail. This declaration does not authorize Meta publish, budget changes, website deploy, Kaspi/WebUI changes, price changes, stock changes, supplier actions, payment, PO, or owner publication.
```

### LINE31 Countrywide Meta Publish

```text
I approve LINE31_COUNTRYWIDE_META_PUBLISH for the final validated creative mapping [mapping_path_or_sha], using the exact campaign/adset/ad specification in the current launch packet, with daily budget [INSERT_KZT], hard cap [INSERT_KZT], landing URL [INSERT_FINAL_LANDING_URL], and Kaspi CTA URL [INSERT_FINAL_KASPI_CTA_URL]. No other Meta, Kaspi, WebUI, website, price, stock, cash, supplier, PO, scheduler, workbook, or database changes are approved.
```

### Website Deploy

```text
I approve ACMEWEAR_WEB_LINE31_DEPLOY for commit/build [HASH], limited to [EXACT ROUTE/TRACKING CHANGE]. No price, offer, stock, Kaspi, Meta, CRM, database, workbook, scheduler, supplier, payment, or PO change is approved.
```

### Internal Kaspi Isolation Dry Run

```text
OWNER APPROVES READ-ONLY LINE31 INTERNAL KASPI ISOLATION DRY-RUN ONLY:
Run read-only analysis of how internal Kaspi LINE31 campaigns and seller bonus promotion affect attribution. Do not pause, edit, resume, change bids/budgets, change seller bonus, change price, change stock, or perform any ad-platform writes.
```

### Internal Kaspi Pause Or Isolation Apply

```text
I separately approve LINE31_INTERNAL_KASPI_ISOLATION_APPLY for campaign IDs [INSERT_IDS] and promo [INSERT_PROMO_ID] for the window [START-END]. Preserve organic LINE31 sellability and do not touch non-LINE31 surfaces. This approval is separate from Meta publish.
```

### Source Pointer Or Scheduler Change

```text
I approve LINE31_SOURCE_POINTER_OR_SCHEDULER_CHANGE only for [EXACT FILE/TASK], with dry-run diff [PATH] and rollback [PATH]. No campaign, price, stock, cash, supplier, PO, CRM, WebUI, Kaspi, Meta, or production DB write is approved.
```

### Production DB Or Workbook Write

```text
I approve PRODUCTION_DB_OR_WORKBOOK_WRITE only for [EXACT SURFACE], using backup [BACKUP_PATH], expected diff [DIFF_PATH], and rollback [ROLLBACK_PATH]. No campaign, price, stock, cash, supplier, PO, Meta, Kaspi, WebUI, or owner-publication action is approved.
```

### Price Or Stock Change

```text
I approve [PRICE/STOCK] change only for [EXACT SKU/OFFER/CAMPAIGN], from [OLD] to [NEW], based on evidence [PATH]. No Meta publish, website deploy, supplier, payment, PO, CRM, scheduler, DB, or unrelated offer changes are approved.
```

### Cash, Supplier, Or PO Action

```text
I approve [SUPPLIER/PAYMENT/PO ACTION] only for [SUPPLIER], amount [AMOUNT CURRENCY], date [DATE], and purpose [PURPOSE]. This approval does not authorize Meta, website, Kaspi, WebUI, price, stock, CRM, database, workbook, scheduler, or owner-publication changes.
```

## Safety Boundary

This plan authorizes repo-docs/tests/scripts/read-only integration work only when separately approved by the owner. It does not authorize production DB writes, production workbook writes, source-pointer writes, scheduler changes, Web_automation writes, Kaspi/API/WebUI/Meta writes, campaign bid/budget/state changes, price changes, stock changes, cash movement, supplier payment, PO commitment, owner publication, internal Kaspi campaign pause, final Meta publish, or any non-LINE31 live action.
