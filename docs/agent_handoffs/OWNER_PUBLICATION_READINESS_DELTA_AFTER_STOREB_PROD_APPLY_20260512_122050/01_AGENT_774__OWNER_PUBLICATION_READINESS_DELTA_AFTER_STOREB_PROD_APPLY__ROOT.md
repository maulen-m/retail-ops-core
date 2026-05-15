# Agent774 - Owner-Publication Readiness Delta After STOREB Production Apply

## Mission

Run a fresh review-only owner-publication readiness delta after the STOREB owner mapping was applied to production `db/app.db`.

This lane answers one question only:

`What owner-publication blockers cleared because of the STOREB production apply, what blockers still remain, and what is the minimum safe next action?`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_OWNER_MAPPING_PRODUCTION_APPLY_CLOSEOUT_20260512_102321.md`
6. `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/final_blocker_classification.json`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE_C_PLUS_PREP_STARTERS_20260511_154019/02_AGENT_766__OWNER_PUBLICATION_READINESS_DELTA__PARALLEL_ROOT.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent766_owner_publication_delta_closeout.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_PHASE_C_PLUS_SYNTHESIS_20260511_154019.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_20260510_200936.md`
11. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_ACCEPTANCE_PHASE_5_5_20260510_222529.md`
12. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CURRENT_AGENT750_STOPLINE.md`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/owner_publication_readiness_delta_after_storeb_prod_apply_20260512_122050_agent774_closeout.md`

## Assigned Evidence Root

`~/Docs/Autonomous_business/exports/validation/owner_publication_readiness_delta_after_storeb_prod_apply/20260512_122050`

Create this folder if needed. You may write only inside this evidence root and to the assigned closeout above.

## Scope

Allowed:

- Read repo docs, current DB, current workbook metadata, prior closeouts, and validation artifacts.
- Run read-only commands.
- Run validators only when their outputs are contained under the assigned evidence root and they do not mutate production truth.
- Write evidence files only under the assigned evidence root.
- Write the assigned closeout.

Forbidden:

- No production DB mutation.
- No protected workbook mutation.
- No scheduler, LaunchAgent, plist, cron, or automation enablement.
- No Web_automation writes.
- No browser/session/credential export.
- No external-system writes or sends.
- No Kaspi merchant writes.
- No owner publication, owner send, owner approval request, or owner-facing packet publication.
- No cash movement, supplier payment, PO commitment, ad-spend mutation, price change, or stock change.
- No `--apply` unless the command is proven to write only inside the assigned evidence root. If unsure, do not run it.

## Required READCHECK

In the closeout, record:

- current timestamp;
- current `db/app.db` SHA-256;
- current `db/app.db` mtime;
- `PRAGMA integrity_check` result from read-only SQLite;
- `lsof db/app.db` result;
- current protected workbook SHA-256;
- current protected workbook mtime;
- whether current hashes match the latest status JSON after the STOREB production apply;
- explicit note that no workbook, scheduler, external write, owner-publication action, or DB apply was performed.

## Suggested Read-Only Checks

Use judgment, but at minimum compare the current state against Agent766 and the STOREB production-apply closeout.

Safe command examples:

```bash
sqlite3 -readonly db/app.db "PRAGMA integrity_check;"
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
stat -f '%Sm %N' -t '%Y-%m-%dT%H:%M:%S%z' db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
lsof db/app.db
```

If the scripts are available and their outputs can be contained under the assigned evidence root, run:

```bash
python3 scripts/validate_ads_sidecar_readiness.py --db db/app.db --ads-db exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_packet/raw/source/kaspi_marketing.sqlite --as-of 2026-05-11 --output-root exports/validation/owner_publication_readiness_delta_after_storeb_prod_apply/20260512_122050/validators/ads_sidecar_readiness --max-age-hours 72 --readiness-mode apply --strict
python3 scripts/validate_ads_offer_universe_coverage.py --db-path db/app.db --truth-source db --start 2026-05-05 --end 2026-05-11 --as-of 2026-05-11 --output-dir exports/validation/owner_publication_readiness_delta_after_storeb_prod_apply/20260512_122050/validators/ads_offer_universe_coverage --strict
python3 scripts/validate_ads_spend_reality.py --db-path db/app.db --truth-source db --start 2026-05-05 --end 2026-05-11 --as-of 2026-05-11 --output-dir exports/validation/owner_publication_readiness_delta_after_storeb_prod_apply/20260512_122050/validators/ads_spend_reality --strict
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict
```

For any failing validator, capture the failure as evidence and classify it. Do not fix it in this lane.

If you inspect `scripts/run_operational_stock_daily_truth.py`, inspect `--help` first and run it only if you can prove it is read-only/output-contained and will not publish owner output or mutate shared production state.

## Required Analysis

Your closeout must include:

- What Agent766 owner-publication blockers existed before STOREB production apply.
- Which blocker(s), if any, the STOREB production apply actually cleared.
- Which blocker(s) still remain.
- Whether STOREB ads source truth is now green for `2026-05-05..2026-05-11`.
- Whether all-store owner publication is green or still blocked.
- What exact evidence would clear each remaining blocker.
- The most efficient next options, ranked.

## Gate Rules

Use:

- `Gate: GREEN` only if the readiness delta is fully clear, output-contained, no unauthorized write happened, and the closeout identifies the exact next safe action.
- `Gate: YELLOW` if the delta is clear but owner publication still requires additional proof, review, or authorization.
- `Gate: RED` if the current boundary drifted unexpectedly, outputs escaped the assigned scope, a forbidden write occurred, or any artifact falsely claims owner-publication authority.

The gate must be a standalone line exactly like:

`Gate: YELLOW`

## Completion

After writing the closeout, run the tmux completion command appended by the orchestrator. This run is monitor-only. Do not manually ping any tmux pane or chat.
