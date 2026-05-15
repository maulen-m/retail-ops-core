# Agent841 - Current 16c2 Blocker-Visible Partial Copied-Temp Proof

Run this starter only after Agent840 is reviewed by the orchestrator.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent840_source_fact_synthesis_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent840_source_fact_synthesis/MVOS_SOURCE_FACT_SYNTHESIS_PACKET.md`
7. Prior Agent831 packet: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent831_sales_fact_identity_blockers/SALES_FACT_IDENTITY_DECISION_PACKET.md`
8. Prior Agent834 packet: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent834_exception_queue_reanchor_copy_proof/EXCEPTION_QUEUE_REANCHOR_COPY_PROOF.md`
9. This starter prompt.

## Assignment

Execute the `CURRENT_16C2_BLOCKER_VISIBLE_PARTIAL_COPIED_TEMP_PROOF` lane exactly as Agent840 scoped it. This is a current-boundary evidence replay only. It must preserve every unresolved blocker visibly.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent841_current_16c2_partial_copied_temp_proof/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent841_current_16c2_partial_copied_temp_proof/CURRENT_16C2_BLOCKER_VISIBLE_PARTIAL_COPIED_TEMP_PROOF.md`

Required copied DB:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent841_current_16c2_partial_copied_temp_proof/current_16c2_partial_copy.db`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent841_current_16c2_partial_copied_temp_proof_closeout.md`

## Required Work

- Recheck production `db/app.db` SHA and integrity before copying. Expected DB SHA is `16c2a7ab86f2899c75f2aba4158c0b1d39495bf30fe343f049654864a7bd75cd`. If it differs, stop and write a drift closeout. Do not replay stale proof.
- Recheck all-business automation pause state and protected-surface holders.
- Copy production `db/app.db` to the assigned evidence root only after the SHA/integrity and pause checks pass.
- Verify copied DB integrity before and after copied-temp mutations.
- Reanchor/rerun the Agent831 six sales-fact identity decisions on the copied DB, preserving the `914340762` active-map-vs-3XL conflict visibly.
- Reanchor/rerun the Agent834 9-row exception resolution on the copied DB and prove no hidden stock table mutation.
- Attach Agent839 PO owner fact bundle as a source candidate only. Do not clear PO source truth unless a later CodeCaptain answer accepts owner-chat confirmation for copied-temp proof.
- Attach Agent838 lifecycle evidence for exactly the 33 WebUI status-change pairs and keep the 112 residual pairs blocked.
- Attach Agent837 STOREB ads evidence for `11120372b` and `11942309b` only as observed-conversion evidence, and keep `11122298b`, `11391205b`, `11391711b`, and `11956144b` blocked.
- Attach Agent836 compact-SKU COGS options and bank/manual freshness as blocked source-choice rows. Do not clear cashflow or source-freshness.
- Run available copied-DB validators that are safe on a copied DB. Owner publication must remain blocked; this is expected, not a failure.
- Produce a packet that states exactly which slice is green and which domains remain blocked.

## Boundaries

You may mutate only the copied DB under the assigned evidence root.

No production DB write, workbook write, scheduler mutation, source-pointer write, external write, Web_automation mutation, owner publication, cash movement, supplier payment, PO commitment, ad-platform write, stock change, price change, or lifecycle/status production repair.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

## Gate Guidance

Gate: GREEN if the copied-temp partial replay completes against the current `16c2...` copied DB, copied DB integrity remains `ok`, production DB/workbook remain unchanged, Agent831/Agent834 reanchor evidence is produced, and all unresolved blockers are visibly retained.

Gate: YELLOW if replay is incomplete or a source decision is still needed, but production isolation is preserved and the packet is useful.

Gate: RED if production was touched, copied-temp isolation cannot be proven, or the packet would mislead owner-publication readiness.
