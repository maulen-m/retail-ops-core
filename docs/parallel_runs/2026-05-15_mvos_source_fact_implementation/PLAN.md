# MVOS Source Fact Implementation Plan

Created: `2026-05-15 17:44 +05`

Status: `ACTIVE_SOURCE_FACT_COLLECTION_ONLY`

## Purpose

Freeze business automations, collect the missing source facts from the Agent835 MVOS source-decision synthesis, and prepare the next copied-temp proof lane without widening authority.

## Current Freeze Boundary

- Business automation freeze evidence: `~/Docs/Autonomous_business/exports/automation_control/20260515_174424_plan_implementation_freeze/`
- Freeze scope: `all-business`
- Freeze verify result: `0/27 loaded`
- DB SHA-256 after live daily ops and before this implementation wave: `16c2a7ab86f2899c75f2aba4158c0b1d39495bf30fe343f049654864a7bd75cd`
- Workbook SHA-256 after live daily ops and before this implementation wave: `0de67615b86d599f13005c963b2cc310813a310e0c36efd056f2398b44339466`
- DB integrity: `ok`
- Protected DB/workbook holders at pause verification: `0`

This boundary supersedes the Agent835 synthesis awareness boundary `2166e2b3...` for new copied-temp proof planning. Agent835 remains the decision source, not the current live boundary.

## Source Inputs

- Agent835 synthesis packet: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_SOURCE_DECISION_WAVE_SUMMARY.md`
- Agent835 next packet: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_NEXT_CODECAPTAIN_PACKET.md`
- Owner/Web_automation supplement: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_OWNER_WEB_AUTOMATION_SUPPLEMENT_20260515_143545.md`
- Blocker matrix: `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_BLOCKER_MATRIX.tsv`

## Owner-Confirmed Source Updates

- PO-4.0 LINE61 shortage is real: `115` ordered/cargo, `92` actual received, `23` short, size shortages XL `7`, 2XL `5`, 3XL `6`, 4XL `5`.
- Web_automation may be read for strategy, experiment, schedule, offer, price, ads, and source context.
- STOREB ads may be fetched read-only via existing API/Web_automation methods; Headless Playwright or Chrome AutoConnect fallback is approved only for read-only capture.
- WebUI Archive may be used read-only for unresolved Kaspi delivery/lifecycle rules through existing repo methods, Chrome AutoConnect, Codex Computer, or Headless Playwright.
- Existing scripts may load `.env` for read-only authentication, but secrets must not be printed, copied, bundled, or committed.

## Non-Authorization

This plan does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron/plist changes, source-pointer replacement, Web_automation mutation, Kaspi/API writes, ad-platform writes, bank writes, owner publication/send, cash movement, supplier payment, PO commitment, ad spend, stock changes, price changes, or lifecycle/status production repair.

## Parallel Root Agents

Agent836: cashflow compact SKU economics and bank/manual freshness source packet.

Agent837: STOREB ads fresh source capture and mapping-evidence packet.

Agent838: lifecycle/status WebUI Archive route and unresolved-pair evidence packet.

Agent839: PO owner-confirmed shortage replacement-source packet and current-boundary carry-forward notes.

These agents can run in parallel because they have disjoint evidence roots and no production mutation authority.

## Queued Synthesis Agent

Agent840 runs only after Agents836-839 close out and the orchestrator reviews their gates. Agent840 prepares an updated CodeCaptain/Oracle packet and names the exact copied-temp replay route. Agent840 must not run production apply.

## Expected Gate Meaning

- `GREEN`: source facts are sufficient for the assigned lane's next copied-temp proof, with no production mutation.
- `YELLOW`: useful evidence collected, but exact owner/source choice or residual source gap remains.
- `RED`: boundary violation, protected-surface mutation, unsafe external write, or source evidence cannot be trusted.

## Execution Rule

Closeout files and evidence artifacts are authoritative. Tmux pings are wake-up signals only.
