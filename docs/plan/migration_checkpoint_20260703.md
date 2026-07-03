# AB Migration Checkpoint 2026-07-03

Gate: RED_ACCEPTED_CHECKPOINT_ONLY

This is a migratable code/docs checkpoint, not an operational GREEN claim. It records the canonical dirty-set disposition for the Phase 2 truth branch before the separate push wave.

## Scope

- Repo: `~/Docs/Autonomous_business`
- Branch: `greenpath/20260613-phase2-truth`
- Checkpoint message: `checkpoint: Autonomous_business migratable Phase 2 RED snapshot 2026-07-03`
- Tag: `ab-migration-checkpoint-20260703-phase2-red`
- External writes: none
- Push: forbidden in this checkpoint lane

## Accepted RED Blockers

The checkpoint intentionally preserves these known RED blockers:

- parked order `981470351`
- cashfloor stopline
- G-STOCK / daily-truth REDs
- 14-failed-tests state
- stale ArchiveOrders parity blocker

## Dirty-Set Classification

Initial snapshot classifies into these buckets:

| Class | Paths | Decision and reason |
|---|---|---|
| Commit | `.claude/DECISIONS.md`, `.claude/ISSUES.md`, `.claude/PROGRESS.md`, `.claude/SESSION_LOG.md`, `.claude/TASKS.md`, `claude/journal.md` | Existing tracked state/evidence in the snapshot; commit as checkpoint context only, not as business-rule authority. |
| Commit | `config/anchors/kaspi_webui_archive_downloads.json`, `config/bank_accounts.yaml`, `config/bank_accounts_history.yaml`, `config/bank_accounts_history_totals.md`, `config/cashflow_scenarios.yaml`, `config/opex/opex_commitments.csv`, `config/opex/opex_schedule.yaml` | Canonical tracked config changes already present in the dirty set. |
| Commit | `core/cashflow/refund_reserve.py`, `core/ops/customer_size_request.py` | Tracked source changes already present in the dirty set. |
| Commit | `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`, `docs/cashflow/OPEX_OWNER_INPUT_CONTRACT_2026-07-02.md`, `docs/current/LINE31_ACTIVE_GOAL_COMPLETION_AUDIT_CURRENT.md`, `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`, `docs/current/LINE31_LAUNCH_CURRENT_STATUS.md`, `docs/plan/green_path_2026-06/dashboard/progress-data.js`, `docs/plan/green_path_2026-06/green_path_run/DEFERRED_QUEUE.md`, `docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md`, `docs/plan/green_path_2026-06/green_path_run/STATUS.md`, `docs/plan/green_path_2026-06/green_path_run/lease_log.md`, `docs/plan/green_path_2026-06/green_path_run/scoreboard.csv` | Tracked docs/status/dashboard state from the snapshot. |
| Commit | `scripts/build_kaspi_customer_size_cadence_readiness_packet.py`, `scripts/build_kaspi_customer_size_early_send_priority_packet.py`, `scripts/build_kaspi_customer_size_owner_dashboard.py`, `scripts/build_kaspi_customer_size_reply_polling_handoff.py`, `scripts/build_kaspi_customer_size_workflow_readiness_packet.py`, `scripts/cashflow_preflight_po.py`, `scripts/export_sales_archive_statusdate_mapped.py`, `scripts/materialize_temporary_ocr_stock_override.py`, `scripts/rebuild_cashflow_calendar.py`, `scripts/run_green_path_offsite_backup.sh`, `scripts/run_kaspi_customer_size_no_send_green_followup.py`, `scripts/run_kaspi_customer_size_post_canary_sequence.py`, `scripts/translate_orders_to_cashflow_events.py`, `scripts/validate_kaspi_customer_chat_open_no_type_canary_result.py` | Tracked script changes from the snapshot. |
| Commit | `tests/test_cashflow_refund_reserve.py`, `tests/test_cashflow_translator.py`, `tests/test_customer_size_request.py`, `tests/test_export_sales_archive_statusdate_mapped.py`, `tests/test_kaspi_customer_chat_open_no_type_result_validator.py`, `tests/test_temporary_ocr_stock_override.py` | Tracked test changes from the snapshot. |
| Commit | `config/owner_decisions/offer_creation_rules_2026_07_03.json`, `docs/plan/green_path_2026-06/runtime_owner_stock_events/20260628_black_tshirt_oos.md`, `scripts/build_kaspi_customer_size_manual_assist_packet.py`, `scripts/record_kaspi_customer_size_manual_action_outcome.py`, `tests/test_cashflow_anchor_rebase.py`, `tests/test_offer_creation_rules.py` | Selected untracked source/docs/tests from the snapshot; canonical checkpoint payload. |
| Commit | `docs/plan/migration_checkpoint_20260703.md` | New consolidation note required by the checkpoint contract. |
| L2-only uncache | `runtime/playwright/kaspi_webui_archive_session_11KZ.json` | Playwright session JSON is session/runtime material; keep the working copy locally but remove it from git tracking. Existing `.gitignore` already excludes `runtime/playwright/*session*.json`. |
| L2-only uncache | `runtime/playwright/kaspi_webui_archive_session_MELVIS.json` | Playwright session JSON is session/runtime material; keep the working copy locally but remove it from git tracking. Existing `.gitignore` already excludes `runtime/playwright/*session*.json`. |
| Leave dirty | `.claude/settings.local.json` | Local agent permission/settings file; not canonical repo state. |
| Leave dirty | `scripts/run_green_path_offsite_backup.sh.bak_20260702` | Local backup copy of a tracked script; preserve outside the checkpoint commit unless a later owner-approved cleanup lane decides otherwise. |

## Checkpoint Rules

- Do not stage via `git add -A`.
- Stage only classified commit paths from the initial snapshot plus this note.
- Re-check `.claude` tracked-state hashes before commit to ensure no other agent changed those files mid-run.
- Run secret-shape scan over every to-be-committed file before commit.
- Run checkpoint gates after commit/tag and report known REDs honestly.

## Rollback

- If the checkpoint commit is wrong before push: delete local tag `ab-migration-checkpoint-20260703-phase2-red`, then revert the checkpoint commit.
- If a later push wave is approved and then found bad: stop for owner approval before any history rewrite.
