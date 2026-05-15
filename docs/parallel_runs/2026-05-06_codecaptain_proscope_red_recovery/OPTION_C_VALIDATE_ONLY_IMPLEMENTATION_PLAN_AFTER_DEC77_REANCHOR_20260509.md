# Option C Validate-Only Implementation Plan After Current dec77 Re-Anchor

Generated: 2026-05-09
Owner surface: Autonomous_business CodeCaptain recovery lane
Plan status: validate-only planning GREEN, production scheduler/write authority BLOCKED

This document replaces the stale post-Agent742 Option C planning surface for current-boundary work. It is a plan and starter-pack skeleton only. It does not authorize production scheduler automation, workbook mutation, DB mutation, external writes, owner decision publication, or Option C production launch.

## 1. Current Authority And Boundary

Current boundary authority is the Agent746 forensics plus Agent747/748/749 closeout chain:

| Item | Current value | Use in this plan |
|---|---:|---|
| Production DB | `~/Docs/Autonomous_business/db/app.db` | Boundary source only; no mutation |
| Current DB SHA-256 | `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64` | Required start/final sample for future copied-DB runs |
| Protected workbook | `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx` | Protected UI/input contract; no mutation |
| Protected workbook SHA-256 | `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c` | Required start/final sample for future runs |
| Current release anchor | `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/` | Current release-anchor evidence |
| Agent747 | `YELLOW` | Current `dec77` release anchor exists, backup exists, validators pass; review needed for dirty-state/holder context |
| Agent748 | `YELLOW` | Independent current-boundary confirmation; non-RED with holder/dirty-state review notes |
| Agent749 | `GREEN` | Strict daily preflight proof-window hardening landed |

Agent749 hardening is now part of the current planning contract:

- `scripts/run_strict_daily_preflight.py` checks `AB_PROOF_WINDOW_LOCK_PATH` or default `config/proof_window.lock`.
- If the lock exists, strict daily preflight exits `75` before DB/workbook/validator/business-insides/drift-pack work.
- The machine-greppable stop string is `STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK`.

The lock behavior is protective only. This plan must not create, remove, install, or schedule the real lock.

## 2. Superseded Authority

The stale Agent742 production boundary was:

`9c51...ee53` (full stale SHA in earlier release artifacts)

Agent746 showed the actual production DB had drifted to:

`dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`

Therefore:

| Prior artifact | Current use | Reason |
|---|---|---|
| Agent742 DB-only repair apply boundary | Historical apply context only | It does not match the current production DB SHA |
| Agent743 release anchor | Superseded, not current authority | It was rooted in the stale Agent742 boundary and went RED/stale after drift |
| Agent744 independent confirmation | Superseded, not current authority | It confirmed the wrong/stale boundary for current production planning |
| Stale Agent745 Option C plan/starter | Superseded, not current authority | It depended on Agent743/744 instead of Agent747/748/749 |

Do not use Agent743, Agent744, or stale Agent745 as current boundary authority. Their process language may be useful only as historical context after replacing every boundary dependency with Agent746/747/748/749 and the current `dec77` anchor.

## 3. Option C Validate-Only Meaning

Option C validate-only means a daily system may be designed and dry-run with:

- copied DB or explicit read-only DB access;
- deterministic evidence folders;
- source freshness checks;
- trust banners;
- exception queues;
- owner brief drafts;
- proof-window controls.

Option C validate-only does not authorize:

- production scheduler installation or launchd/plist mutation;
- production DB writes;
- workbook writes;
- external writes to Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos;
- publication of owner PnL/cash/PO/ad decisions as production GREEN;
- owner approval requests;
- reuse of the old Agent54 phrase or activation of Agent64.

## 4. Validate-Only Daily Workflow

The daily workflow should be implemented only after CodeCaptain review of this plan. It must be deterministic, evidence-first, and fail closed.

1. **Run envelope**

   Record timestamp, git commit/branch/status, operator, as-of date, mode, proof-window lock path, and all output paths before any DB access. The runner must have an explicit `--mode copied-db` or equivalent read-only mode. Default must not write.

2. **Proof-window guard**

   Before opening production DB or workbook, check `AB_PROOF_WINDOW_LOCK_PATH` and default `config/proof_window.lock`. If a lock exists and the runner would read or copy production DB/workbook, exit `75` with `STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK path=<path>`. If the runner is pointed to an already-copied DB under the evidence folder, it may continue without opening production DB and must record that production was not touched.

3. **Current-boundary sample**

   Sample the production DB/workbook SHA only when no proof-window lock blocks production reads. Required expected values are `dec77...ee64` for DB and `3ad4...025c` for workbook. Any mismatch is `BLOCKED`.

4. **Holder and sidecar check before copy**

   Run `lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true` and check for `db/app.db-wal`, `db/app.db-shm`, and `db/app.db-journal`. Copy production DB only when no unsafe holders or sidecars are present. Holder ambiguity is at least `WARNING`, and unsafe holder/sidecar state is `BLOCKED`.

5. **Copied DB creation**

   Create a DB copy inside the deterministic evidence folder, never beside production. Run `PRAGMA integrity_check` on the copy. Record copy SHA, size, mtime, source SHA, copy command, and integrity result. Existing CodeCaptain guidance prefers exact boundary clarity; raw byte copy is appropriate only after the holder/sidecar check is clean.

6. **Source freshness and validator matrix**

   Run validators against the copied DB or explicit read-only path. No validator may silently fall back to production DB. Any command that lacks a copied-DB/read-only contract must be blocked until it is wrapped or tested.

7. **Exception queue materialization**

   Emit exception queues as evidence artifacts only. Warning cohorts must remain visible, including product-identity quarantine, header-only source gap, ads missingness, cashflow coverage gaps, stale sources, and any validator-visible warning counts.

8. **Trust banner classification**

   Classify each owner-output surface as `GREEN`, `WARNING`, or `BLOCKED` for validate-only drafting. The banner must say which decisions are allowed and blocked. Validate-only `GREEN` is not production authority.

9. **Owner brief draft**

   Generate a draft only under the evidence folder. Do not write workbook, send messages, post to external systems, or install scheduler automation. Drafts must include the trust banner and exception links at the top.

10. **Closeout and final boundary sample**

   Re-sample production DB/workbook SHA if production was read at start. Confirm no production DB/workbook/scheduler/external mutation occurred. Write a closeout with gate, command list, evidence index, stoplines, and next action.

## 5. Data Inputs And Freshness Gates

| Surface | Required input | Freshness / proof gate | Validate-only output |
|---|---|---|---|
| Orders/status | Canonical DB order status tables and source refresh metadata | Source freshness strict pass for the as-of date; no unreviewed post-as-of leakage; status source timestamps recorded | Status exception queue and owner draft facts |
| Sales/order entries | Real order-entry rows plus quarantine tables | Product identity must be evidence-backed; do not convert header-only rows into product truth; preserve `23` product-identity warnings, `252` header-only table rows, validator-visible header-only warning count, and total warning count | Sales truth coverage matrix and quarantined-row warnings |
| Stock ledger/snapshot | Stock ledger, operational snapshot, source freshness rows | Operational stock integration gate must be `GREEN` or warning-only; negative balances and missing coverage are not hidden | Stock risk queue and stock confidence banner |
| Ads | Ads scope config, ads source refresh runs, campaign/product daily rows | Missing ads data is never zero spend; active scope must be explicit; stale source refresh blocks ad decision claims | Ads freshness queue and ad trust banner |
| Cashflow | Cashflow event/daily tables, bank statement coverage, payout model config | Order/cashflow coverage pass; actual/model separation pass; invariants pass; `last_statement_date` shown; cash preservation matrix unchanged | Cash Risk Daily draft and cash exceptions |
| PO/inbound/cargo/supplier obligations | PO docs/tables, inbound/cargo records, supplier obligation records | Source paths and as-of timestamps recorded; missing obligation source is `WARNING` or `BLOCKED` depending on decision impact | Obligation risk queue, not payment authority |
| Exception queues | Validator findings and domain-specific exception tables | Cohorts are preserved by code and evidence, not summarized away | Machine-readable JSON/TSV plus owner-readable summary |
| Owner outputs | Draft Markdown/JSON only | Must include trust banner, current boundary, evidence path, generated time, blocked decisions, and source age | Draft only; no send/publish/write authority |

## 6. First Owner-Output Surface

Recommended first surface: **Cash Risk Daily**.

Why Cash Risk Daily first:

- CodeCaptain already recommended it before Owner Profit Daily and PO/SKU Daily.
- It can start with explicit actual/model separation, cash preservation checks, and `last_statement_date` trust banners.
- It is easier to fail closed because missing bank/cashflow coverage can be labeled `BLOCKED` without inventing sales/product truth.
- It is high-value for owner awareness but still safe as a draft-only artifact when no money movement or supplier payment authority is implied.

Required Cash Risk Daily fields:

| Field | Requirement |
|---|---|
| `surface` | `Cash Risk Daily` |
| `mode` | `validate_only` |
| `as_of_date` | Explicit date, no relative-only wording |
| `db_boundary_sha` | Current `dec77...ee64` source boundary plus copied DB SHA |
| `workbook_sha` | Protected `3ad4...025c` sample, if workbook was read |
| `last_statement_date` | Required for decision-grade cash language |
| `actual_vs_modelled_status` | `GREEN`, `WARNING`, or `BLOCKED` |
| `cash_preservation_status` | Must preserve the current matrix; mismatch is `BLOCKED` |
| `blocked_decisions` | Cash movement, supplier payment, PO commitments, ad spend, external sends |
| `allowed_decisions` | Review exceptions, request source refresh, approve later implementation review |
| `evidence_path` | Deterministic folder path |

## 7. Trust Banner Schema

Every validate-only owner output must start with a machine-readable banner. Suggested JSON sidecar schema:

```json
{
  "surface": "Cash Risk Daily",
  "mode": "validate_only",
  "banner_status": "GREEN|WARNING|BLOCKED",
  "generated_at": "YYYY-MM-DDTHH:MM:SS+ZZZZ",
  "as_of_date": "YYYY-MM-DD",
  "db_boundary_sha": "dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64",
  "copied_db_sha": "<sha256>",
  "workbook_sha": "3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c",
  "proof_window_lock_state": "absent|present|not_checked_already_copied_db",
  "source_freshness_status": "GREEN|WARNING|BLOCKED",
  "validator_status": "GREEN|WARNING|BLOCKED",
  "warning_cohorts": [],
  "blocked_decisions": [],
  "allowed_decisions": [],
  "last_statement_date": "YYYY-MM-DD|null",
  "evidence_path": "<absolute_path>"
}
```

Trust banner semantics:

| Banner | Meaning | Allowed owner decisions | Blocked owner decisions |
|---|---|---|---|
| `GREEN` | All critical validate-only gates pass on copied/read-only evidence; warning cohorts are visible; no production mutation | Review draft, review exceptions, request data/source refresh, authorize a later implementation review | Cash movement, supplier payment, PO commitment, ad spend, pricing/stock changes, workbook writes, scheduler enablement, external sends |
| `WARNING` | Core draft may be readable, but one or more non-critical source, holder, dirty-state, or warning-count ambiguities require review | Same as `GREEN`, plus triage warnings before relying on affected sections | Same as `GREEN`; affected operational decisions also blocked |
| `BLOCKED` | A critical source, SHA, integrity, validator, leakage, cash preservation, or warning-visibility gate failed | Review blocked-output reasons only | All operational decisions and any green-style owner brief |

Validate-only `GREEN` means the draft evidence is internally consistent. It does not mean production decision authority.

## 8. Validate-Only Runner Design

Recommended command shape:

```bash
python3 scripts/run_option_c_validate_only.py \
  --as-of YYYY-MM-DD \
  --mode copied-db \
  --evidence-dir exports/validation/option_c_validate_only/YYYY-MM-DDTHHMMSSZ \
  --surface cash-risk-daily
```

Required runner properties:

- Default mode is non-writing and validate-only.
- The runner refuses to continue before any production DB/workbook open if proof-window lock exists and production read/copy is requested.
- The runner may operate on an already-copied DB only if the copy path is explicit and inside the deterministic evidence folder.
- The runner never installs, edits, or enables launchd/plist automation.
- The runner never writes production DB.
- The runner never writes `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- The runner never writes external systems.
- All generated owner outputs are draft files under evidence.
- All validators receive an explicit copied-DB/read-only target or are skipped as `BLOCKED_UNSUPPORTED_VALIDATOR_DB_TARGET`.
- Final closeout includes production SHA re-sample when production was sampled at start.

Deterministic evidence folder shape:

```text
exports/validation/option_c_validate_only/<timestamp>_<as_of>/
  00_run_envelope.json
  01_boundary_start.txt
  02_holder_sidecar_check.txt
  03_db_copy/
  04_validator_outputs/
  05_exception_queues/
  06_owner_drafts/
  07_trust_banners/
  08_boundary_final.txt
  EVIDENCE_FILE_INDEX.tsv
  CLOSEOUT.md
```

## 9. Validator Matrix

Minimum current-boundary matrix for the first implementation:

| Gate | Command family | Required result |
|---|---|---|
| Boundary sample | `shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx` | DB `dec77...ee64`, workbook `3ad4...025c` |
| DB integrity | `sqlite3 -readonly <copied_db> 'PRAGMA integrity_check;'` | `ok` |
| Source freshness | `python3 scripts/validate_policy_source_freshness.py --strict --json` with copied-DB/read-only target | pass |
| Operational stock | `python3 scripts/validate_operational_stock_integration_gates.py --json` with copied-DB/read-only target | `GREEN` with warning-only findings |
| Order/cashflow coverage | `python3 scripts/validate_order_cashflow_coverage.py --as-of <as_of> --strict --json` | pass |
| Actual/model separation | `python3 scripts/validate_cashflow_actual_model_separation.py --anchor-date <as_of> --strict --json` | pass |
| Cashflow invariants | `python3 scripts/validate_cashflow_invariants.py` with copied-DB/read-only target | pass |
| Warning visibility | SQL/JSON probes for product-identity, header-only, ads, leakage, and cash preservation cohorts | preserved and visible |
| No production mutation | before/after SHA/stat for DB/workbook plus git status | unchanged |
| Proof-window lock | focused tests from Agent749 plus runner-level guard test | exits before DB open |

The inherited pinned proof date is `2026-05-04`. Future daily validate-only runs must parameterize the as-of date and record it explicitly; they must not silently mix pinned proof semantics with a new operating date.

## 10. Tests Required Before Any Future Production Scheduler Lane

These tests are required before a future lane may even request production scheduler/write authority:

- A failing-first test proving the validate-only runner exits before opening production DB when `AB_PROOF_WINDOW_LOCK_PATH` exists.
- A failing-first test proving default `config/proof_window.lock` is honored before DB open.
- A test proving every validator command receives an explicit copied-DB/read-only target and cannot silently use `db/app.db`.
- A test proving owner brief generation writes only inside the deterministic evidence folder.
- A test proving workbook path writes are impossible in validate-only mode.
- A test proving external clients are not invoked in validate-only mode.
- Trust banner tests for `GREEN`, `WARNING`, and `BLOCKED`.
- Warning-cohort tests preserving `23` product-identity warnings, `252` header-only table rows, the validator-visible header-only warning count, and total warning findings.
- Cash preservation and leakage tests.
- Scheduler-adjacent tests proving no launchd/plist install path is reached.

Passing these tests would still not authorize a production scheduler. They are prerequisites for a later approval/review lane.

## 11. Stoplines Before Scheduler Or Write Authority

Stop `RED` before any scheduler/write request if any of these occur:

- current DB SHA differs from `dec77...ee64` without reviewed re-anchor;
- workbook SHA differs from `3ad4...025c`;
- DB integrity fails on production sample or copied DB;
- proof-window lock can be bypassed before DB open;
- any validator silently falls back to production DB;
- production DB/workbook stat or SHA changes during validate-only;
- warning cohorts are hidden, merged away, or treated as product truth;
- `23` product-identity warnings, `252` header-only table rows, validator-visible header-only warning count, or total warning count are not recorded;
- ads missingness is treated as zero spend;
- cash preservation or actual/model separation mismatches;
- owner brief claims production GREEN for cash, PO, ads, stock, PnL, or pricing;
- launchd/plist/scheduler mutation is proposed without explicit later owner approval;
- external writes or browser/Web_automation actions are proposed;
- old Agent54 phrase reuse or Agent64 activation appears.

Stop `YELLOW` if validators pass but dirty-state, holder ambiguity, non-critical source freshness ambiguity, or CodeCaptain review gaps remain.

## 12. Next Helper-Agent Wave

Do not launch implementation agents until this Agent750 plan is reviewed, CodeCaptain returns the GREEN decision token, and `scripts/check_agent750_launch_readiness.py` returns `"ok": true`. The safe next wave after review has one write-capable implementation agent maximum:

| Agent | Type | Dependency | Scope |
|---|---|---|---|
| Agent751 | Sole write-capable implementation agent | After Agent750 plus CodeCaptain GREEN review and readiness checker `"ok": true` | Implement tests-first validate-only runner contract, copied-DB/read-only targeting, proof-window guard, deterministic evidence folder, and Cash Risk Daily draft stub |
| Agent752 | Read-only analyst | Parallel after review | Specify Cash Risk Daily owner-output fields, trust banner language, and allowed/blocked decisions |
| Agent753 | Read-only analyst | Parallel after review | Map source freshness, exception queues, warning cohorts, and validator gaps for implementation |

Starter prompt drafts are placed under:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/starter_prompts/`

The wave must keep one write-capable implementation agent maximum. Analysts write only assigned handoff/evidence artifacts, not shared repo code or production state.

## 13. Human Approvals Required Later

Later explicit human approval is required for:

- any production scheduler installation, launchd/plist mutation, or recurring automation enablement;
- any production DB write path;
- any workbook write path;
- any external write to Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos;
- any owner-facing publication channel outside local evidence folders;
- any owner decision workflow that recommends or triggers cash movement, supplier payment, PO commitment, ad spend, price changes, stock changes, or PnL/cash/PO production GREEN decisions.

CodeCaptain review is not a substitute for owner approval. Owner approval must be explicit in a later lane.

## 14. CodeCaptain Review Recommendation

CodeCaptain review is required before implementing validate-only runner code because this plan touches scheduler-adjacent safety, owner-output trust banners, and copied-DB/read-only validator contracts.

Recommended CodeCaptain pack:

- this plan document;
- Agent746 forensics closeout;
- Agent747 closeout and `CURRENT_DEC77_RELEASE_ANCHOR.md`;
- Agent748 independent confirmation closeout;
- Agent749 proof-window hardening closeout;
- starter prompt drafts for Agents751, 752, and 753;
- a short manifest listing the current DB/workbook SHA boundary, warning cohorts, planned write boundaries, stoplines, and human approvals required later.

Ask CodeCaptain only to review the validate-only plan and starter-pack skeleton. Do not ask for production scheduler approval, owner authorization, workbook write approval, external write approval, old Agent54 phrase reuse, or Agent64 activation.
