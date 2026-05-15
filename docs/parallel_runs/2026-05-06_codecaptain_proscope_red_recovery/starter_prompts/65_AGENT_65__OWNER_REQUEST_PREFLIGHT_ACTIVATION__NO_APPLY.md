# Agent 65 - Owner-Request Preflight / Activation Packet, No Apply

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_owner_request_preflight_activation_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/`

## Mission

Prepare the next owner-request preflight/activation packet for review.

This is not a production apply lane and not an owner-request lane. It is an evidence-only preflight lane that may prepare a review-required active owner-request packet candidate, but it must not show that packet to the owner, ask the owner for the phrase, or mutate production.

## Bootstrap Context

Before writing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT64_INACTIVE_DRAFT_ACCEPTANCE_20260507.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-07/131850_TASK-000_codecaptain-agent64-inactive-owner-phrase-review/Answer/Code_Captain_2026-05-07_13_56_00.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_evidence/OWNER_AUTHORIZATION_PHRASE_DRAFT__INACTIVE_REVIEW_REQUIRED.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_evidence/OWNER_PHRASE_DRAFT_REVIEW_CHECKLIST.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT64_ORCHESTRATOR_REVIEW_20260507.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_62_pinned_reproof_after_asof_fix_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_conditional_ws4_readiness_pack_for_codecaptain_closeout.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_owner_request_preflight_activation_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/**`

Allowed reads:

- production `~/Docs/Autonomous_business/db/app.db`
- production `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- repo scripts/docs needed for read-only validators
- Agent61/62/63/64 evidence

Forbidden:

- Do not mutate production `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers or pause/unload jobs.
- Do not call or write to live APIs, web UIs, browser automation, banks, Kaspi, ads platforms, Google, Web_automation, or external systems.
- Do not ask the owner for the phrase.
- Do not present the packet as ready to show owner unless every preflight item passes and it is still marked `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`.
- Do not run any `--apply` command against production.
- Do not use ad hoc SQL to mutate anything.
- Do not reuse, quote as active, or request the old Agent54 owner phrase.

## Required Evidence

Create these files in the assigned evidence folder:

1. `EVIDENCE_MANIFEST.md`
2. `FRESH_PRODUCTION_BOUNDARY_REPORT.md`
3. `BACKUP_ROLLBACK_EVIDENCE.md`
4. `PINNED_VALIDATOR_MATRIX.tsv`
5. `FRESH_ROW_COUNT_MATRIX.tsv`
6. `FRESH_LEAKAGE_MATRIX.tsv`
7. `OWNER_REQUEST_PACKET__REVIEW_REQUIRED_NOT_SENT_TO_OWNER.md`
8. `CODECAPTAIN_AGENT65_REVIEW_REQUEST_PROMPT.md`

The preflight must capture:

- current production DB SHA256;
- current workbook SHA256;
- DB and workbook mtimes;
- `PRAGMA integrity_check` result for production DB;
- SQLite sidecar files near `db/app.db`;
- `lsof` holders for production DB and sidecars;
- timestamped DB backup path, SHA256, and integrity if safe to create;
- timestamped workbook backup/copy path and SHA256 if safe to create;
- rollback command or rollback procedure;
- pinned validator matrix for the `2026-05-04` contract or explicitly reviewed equivalent;
- fresh production row-count matrix for Agent62 contract tables;
- fresh production post-as-of leakage matrix for `order_status_event`, `sales_fact_v2`, `stock_ledger`, `fact_cashflow_events`, and `fact_cashflow_daily`;
- explicit visibility of Agent63 YELLOW items: `912298499`, `912168984`, workbook tail rows `8053-8137`, `23` STOREB quarantine residuals, and Option C validate-only.

Suggested read-only commands, adapt safely if repo scripts require different flags:

```bash
shasum -a 256 ~/Docs/Autonomous_business/db/app.db
shasum -a 256 ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
stat -f '%Sm %N' ~/Docs/Autonomous_business/db/app.db
stat -f '%Sm %N' ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
find ~/Docs/Autonomous_business/db -maxdepth 1 -name 'app.db-*' -print
lsof ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/db/app.db-wal ~/Docs/Autonomous_business/db/app.db-shm 2>/dev/null || true
sqlite3 ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'
```

If and only if sidecar/lsof state is safe, create backup copies under the assigned evidence folder. Prefer SQLite `.backup` for the DB:

```bash
sqlite3 ~/Docs/Autonomous_business/db/app.db ".backup '<assigned_evidence_folder>/backups/app_db_before_owner_request_preflight_YYYYMMDD_HHMMSS.db'"
```

Do not overwrite existing backup files.

## Gate Semantics

`GREEN`:

- All fresh boundary checks are present.
- DB integrity is `ok`.
- SQLite sidecar/lsof state is safe.
- Backup path/SHA/integrity and rollback procedure are present.
- Pinned validators pass.
- Row-count and leakage matrices are present and match the reviewed boundary or every difference is explicitly reviewed-safe.
- Owner request packet is review-required, not sent to owner, and cannot be confused with live authorization.
- No production/workbook/scheduler/external mutation occurred.

`YELLOW`:

- Evidence is useful, but the owner-request packet needs CodeCaptain/orchestrator revision before it can be shown to owner.
- Examples: validators pass but wording needs review; backup evidence exists but a non-blocking ambiguity remains; row-count differences require explicit review.

`RED`:

- Any production DB/workbook/scheduler/external mutation occurred.
- Owner authorization was requested.
- The packet is shown as owner-ready before review.
- Old Agent54 phrase is reused or requested.
- DB integrity is not `ok`.
- Unsafe SQLite sidecar/lsof state exists.
- Backup/SHA/integrity/rollback proof is missing.
- Required pinned validators fail or are skipped.
- Post-as-of leakage appears without reviewed explanation.
- Row-count matrix differs without reviewed explanation.
- Agent63 YELLOW items are hidden or softened.
- Workbook tail rows `8053-8137` are allowed to feed another send build before canonical status refresh.
- `912168984` is shipped or repaired without bounded current-status check and manual size confirmation.
- Option C is promoted beyond validate-only.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN/YELLOW/RED` line;
- READCHECK list;
- exact files written;
- exact commands run and pass/fail summary;
- current DB SHA and workbook SHA;
- DB integrity result;
- sidecar/lsof summary;
- backup/rollback summary;
- validator summary;
- row-count/leakage summary;
- explicit mutation statement;
- whether any owner-facing packet remains review-only;
- whether CodeCaptain review is recommended before owner request;
- recommended next step for orchestrator.
