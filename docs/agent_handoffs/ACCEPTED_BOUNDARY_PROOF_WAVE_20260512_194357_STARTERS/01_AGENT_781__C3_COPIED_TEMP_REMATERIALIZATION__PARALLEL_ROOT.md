# Agent781 Starter: C3 Copied-Temp Rematerialization

You are Agent781. Execute only this assigned review-only lane.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_REVIEW_ONLY_20260512_194357.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent779_current_boundary_freeze_and_post_root_drift_forensics_20260512_191139_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent780_automation_quiet_window_audit_20260512_191139_closeout.md`
7. This starter prompt: `~/Docs/Autonomous_business/docs/agent_handoffs/ACCEPTED_BOUNDARY_PROOF_WAVE_20260512_194357_STARTERS/01_AGENT_781__C3_COPIED_TEMP_REMATERIALIZATION__PARALLEL_ROOT.md`

## Mission

Build the fastest safe copied-temp C3 proof on the accepted boundary. Use a copied DB only. Do not mutate production `db/app.db` or the protected workbook.

Required first checks:

- Confirm `db/app.db` SHA is `7cfe3ebc5df4867e28c57b4ed392f665dfa8143c44db4d54dde11fdb41f889d6`.
- Confirm `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA is `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`.
- Confirm DB integrity is `ok`.
- Check for SQLite sidecars and DB/workbook holders.

Allowed writes:

- assigned evidence folder under `~/Docs/Autonomous_business/exports/validation/accepted_boundary_proof_wave/20260512_194357/agent781_c3_copied_temp_rematerialization`
- assigned closeout file only
- copied DB files inside the assigned evidence folder

Forbidden:

- production DB mutation
- workbook mutation
- scheduler restore or mutation
- external writes
- browser/login automation
- credential/session reads or export
- owner publication or owner approval request

## Output

Write closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent781_c3_copied_temp_rematerialization_20260512_194357_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- exact accepted boundary recheck evidence
- copied DB path and SHA
- commands run
- C3 copied-temp rematerialization/validation results
- remaining blockers, if any
- explicit statement that production DB/workbook/schedulers/external systems were not mutated

Gate guidance:

- `GREEN`: copied-temp C3 proof completed on the accepted boundary with no forbidden writes and clear next unblockers.
- `YELLOW`: copied-temp proof ran but blockers remain or required script contract is missing.
- `RED`: boundary mismatch, holder/sidecar risk, or forbidden mutation risk.
