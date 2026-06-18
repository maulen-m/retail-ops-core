# Master Remediation Plan — Path to 100% GREEN

**Program goal**: take the Autonomous_business + Web_automation systems from the audited state (truth decay across capital/profit/cash/stock/returns/ads/pricing/automation; PPCH headline 18.92%/30d vs honest 6.0–9.9%) to **100% GREEN as defined by `green_gates.csv` (71 gates)** — with the owner involved exactly once before execution (the `OWNER_DECISION_PACK.md` session) and once at acceptance.

**Authority chain**: this plan consumes `OWNER_DECISIONS_RECORDED.yaml` (decisions), `green_gates.csv` (definition of done), `reconciliation/canonical_numbers.csv` (all numbers; planning values only — see re-baseline rule). Repo contracts (AGENTS.md, WRITE_APPLY_RUNBOOK, WRITE_SIDE_GATING_CONTRACT, cashflow/PO/lifecycle contracts) override this plan wherever stricter. Doc-mtime staleness ≠ contract invalidity (DEF-02): the binding docs stay binding.

**Canonical phase vocabulary**: Phase -1..5 (expert EXT-R01). Mapping from audit P-levels: audit P0 → Phases 1–2 (after backup), audit P1 → Phase 2, audit P2 → Phase 3, audit P3 → Phase 4.

---

## 1. Operating rules (apply to every workstream)

1. **Backup-first**: no repo/DB/workbook/config/scheduler write before G-BCK-01/02/03 pass. The single exception is the pre-authorized day-0 LINE31 ads action (OD-008) — an external, reversible, non-repo action with rollback RB-ADS.
2. **Single-writer invariant** (EXT-A02, G-RDY-04): exactly one write-capable orchestrator. One write lease per repo at a time, granted/revoked/logged by the orchestrator. All analyst/review agents read-only. DB mutations serialize; no two agents ever hold overlapping write scopes.
3. **Dry-run → diff → gate → apply**: every write goes through its script's dry-run with a row-level diff saved, checked against the expected scope (±2% tolerance per OD-015), then `--apply` under its env gate. Any unexpected table/file/SKU/store row in a diff → STOP-THE-LINE.
4. **Re-baseline at entry**: every workstream re-derives its input numbers (read-only) at execution start and records them beside the CN planning values. Planning numbers size the work; execution numbers drive it. (Proven necessary: tranche membership flipped twice in 48h, CN-033/035.)
5. **Docs-before-code** (G-REPO-02): a business-rule change lands in its owning doc in the same changeset, before or with the code.
6. **No secrets/PII** in any artifact, packet, log, or report. Env files referenced by path + presence check only.
7. **Validation per change type** (EXT-V01, commands from the live 130-script inventory): repo change → `pytest -q` + `check_no_db_tracked.sh` (+ `lint_docs.sh` if docs); DB change → backup + dry-run diff + row counts + integrity; cashflow → `validate_cashflow_invariants.py`; PO/dashboard → `validate_po_dashboard_invariants.py`; stock → `validate_ledger.py` + reconciliation; price/upload → fresh inputs (G-PRICE-04) + rollback file (G-WA-02); ads → before/after + CRR report.
8. **Validator-semantics check**: at workstream start, the agent reads its named validators and confirms they check what the gate intends; mismatches are recorded and a correct check substituted (never silently skipped).
9. **Heartbeat**: one status ping at each phase boundary (Telegram once G-ALERT-01 passes; before that, a line in `STATUS.md`). No response expected (OD-029).
10. **Order-header ingestion is sacred** (G-ORD-04): the one alive pipeline must survive every intervention; its freshness validator runs after every scheduler/DB change.

## 2. Runtime ambiguity protocol (zero mid-flight owner contact)

When an agent hits a situation its packet doesn't cover:

1. **Match against the policy table** — the recorded decisions (OD-*) + the standing rules above + the pre-decided edge cases below. If matched: apply, log, continue.
2. **No match → park**: write the item to `DEFERRED_QUEUE.md` (fields: item, lane, kzt_exposure, age_days, fallback_applied, resurfaces_at; default resurface = acceptance). The LANE parks only if the item blocks it; all other lanes continue. Queue entries carry KZT exposure so deferral cost stays measurable (EXT-C04).
3. **STOP-THE-LINE** (the only owner pings, per OD-029): backup/restore failure · unexpected diff rows no policy covers AND >50% of remaining work blocked · evidence of data loss · secret exposure · any live external action outside an approved envelope.

**Pre-decided edge cases** (from reconciliation + expert EXT-B02):
- Count-import replay drives a SKU/size negative → quarantine the SKU (G-STOCK-05 path), never clamp (OD-017).
- Backfill finds COGS-less orders beyond LINE31 → quarantine + continue (expert Phase 2 rule).
- EOD apply surfaces a NEW strict-gate failure class → stop that lane, park with exposure, others continue; never reclassify (OD-016).
- A "dead" storefront shows a live order mid-run → park the disposition action, log, continue (OD-027 executes at its scheduled step regardless).
- Tranche sells out early → scale within the OD-018 envelope only; never exceed cap/tier.
- DB schema drift vs plan assumptions → re-baseline; if structural, park the lane.
- Bank divergence persists on later days after anchor → anchor is truth, log divergence, do not chase mid-program (G-CASH-02 measures it weekly).
- Validator contradicts its gate's intent → rule 8 above.
- A required artifact (count file, snapshot doc) fails checksum → STOP-THE-LINE only if it blocks >50%; else park.

## 3. Workstreams

Effort: S = hours, M = 1–2 days, L = 3–5 days (agent wall-clock, not calendar). Lane = executing agent type per the global orchestration protocol (Codex 5.5 x-high `/goal` packets for precise backend work; Fable 5 for judgment-heavy lanes; Opus 4.8 reviews every diff before apply). Full dispatch packets: `starter_pack/`.

| WS | Phase | Objective | Gates owned | OD inputs | Lane | Effort | Depends on |
|---|---|---|---|---|---|---|---|
| WS-LINE31GUARD | -1 (day 0) | LINE31 ads pause/cap (bleeding-stopper) | (G-LINE31-01 prep) | OD-008/020 | Orchestrator (external console) | S | none |
| WS-BCK | -1 | Freeze, full backup, restore tests, manifest | G-BCK-01..03, G-ORD-04 | OD-001/022/023 | Codex + Orchestrator verify | M | owner session |
| WS-READY | 0 | Dry-run inventory → go/no-go table; rollback rehearsals (scratch); write-gating + lease protocol | G-RDY-01..04, G-REPO-01..02 | OD-015/028/029 | Codex; Opus review | M | WS-BCK |
| WS-INFRA | 1 | Stable venv + repoint 8 jobs; per-job EX_CONFIG diagnosis; Telegram plumbing + forced-failure proof; offsite backup; supervised EOD | G-SCHED-01..03, G-ALERT-01..02, G-BCK-04, (G-SCHED-04 starts) | OD-015/016/024/031 | Codex (2 packets: scheduler, alerting) | M | WS-READY |
| WS-LINES | 2 | Backfill 657-order entries hole (idempotent); restart status events; freshness guards | G-ORD-01..03 | — | Codex | M | WS-INFRA |
| WS-PROFIT | 2 | COGS recognition restart + Mar–Jun backfill; sales chain unfreeze; April restatement | G-COGS-01..04 | OD-014/015 | Codex; Opus review on backfill diff | L | WS-INFRA (EOD), WS-FX (for COGS-less subset) |
| WS-FX | 2 | FX refresh + weekly cadence; landed-cost policy; single COGS authority collapse | G-FX-01..02 | OD-013/003 | Codex; Fable review (authority doc) | M | WS-BCK |
| WS-CASH | 2 | Fresh bank anchor (governed); cashflow rebuild; weekly re-anchor; divergence retirement | G-CASH-01..03 | OD-002/013 | Codex; Opus review | M | WS-READY (rehearsal), WS-FX, B1 drop |
| WS-STOCK | 2 | INBOUND booking → BOTH count imports (precedence per OD-004) → snapshot rebuild → clamp governance → confidence score | G-STOCK-01..05 | OD-004/017 | Codex (strict sequence, single packet); Opus review per step | L | WS-INFRA; ordering INTERNAL and absolute |
| WS-RETURNS | 2 | Pickup predicate; QC event writer; re-entry/loss wiring; comeback telemetry | G-RET-01..03 | OD-006/026 | Codex | M | WS-INFRA |
| WS-ADS | 2 | Canonical backfill 03-04→present; refresh restart; CRR/zero-GMV daily check; campaign⇄SKU map | G-ADS-01..03 | OD-019 | Codex | M | WS-INFRA |
| WS-QUAR | 2 | Triage 297 rows per OD-025 defaults; dispose 657 unquarantined; drain 9 exceptions; exposure metric; op-stock job | G-QUAR-01..04, G-SCHED-05 | OD-025 | Codex; Fable for ambiguous rows | M | WS-LINES (backfill resolves many) |
| WS-RESID | 2 (parallel) | Supervised residual settlement apply (120 / 425,015.24) | G-RESID-01 | OD-015 | Codex; Opus review of diff | S | WS-READY |
| WS-PRICE | 2→3 | Floor single-source (v7 path or v6 reaffirm); WA input refresh; vintage logging; leak stop; backlog re-measure | G-PRICE-01..05, G-WA-02 | OD-003/032 | Fable (floor economics) + Codex (plumbing) | L | WS-FX (v7 path only) |
| WS-RELIST | 3 | Live offer fetch; size-scoped relists; recovery-slope measurement | G-DARK-01..02 | OD-033 | Codex (fetch/upload) + Orchestrator check | S | WS-STOCK |
| WS-LIQ | 3 | Fresh register re-run + segmentation; tranche-1 (11 families); ladder ops; envelope tranches; LINE51 after count | G-LIQ-01..04, G-WA-01, G-CASH-04 | OD-005/011/018/032 | Fable (tranche economics) + Codex (execution); Opus review per tranche file | L | WS-STOCK, WS-PRICE, G-WA-01 live |
| WS-STOREFRONT | 3 | MELVIS/11KZ disposition executed; LINE31 standing spend-vs-stock cross-check job | G-STORE-01, G-LINE31-01 | OD-027, OD-008/020 | Codex | S | G-STOCK-03 (for the LINE31 cross-check; the day-0 cap itself is WS-LINE31GUARD's prep) |
| WS-OPS-TELEMETRY | 3 | Incident KZT lines; 30d collection | G-OPS-01 | OD-030 | Codex | S | WS-INFRA |
| WS-PO-GOV | 3→4 | Stop-buy gates encoded; governed-OFF state; size priors rebuild + 7 tests; forecast loop | G-PO-01..03 | OD-009 | Codex; Opus review (tests) | L | WS-PROFIT, WS-STOCK, WS-RETURNS |
| WS-METRICS | 4 | PPCH v1 + confidence; dashboard cadences; contribution; capital-hours | G-MET-01..04 | OD-010 | Fable (metric spec) + Codex (build) | L | Phase 2 green |
| WS-ACCEPT | 5 | Scored matrix; before/after; deferred-queue review; waivers; owner sign-off; final handoff | G-ACC-01, G-SCHED-04 final | all | Orchestrator + Opus audit | M | everything |

**Critical path**: WS-BCK → WS-READY → WS-INFRA → WS-STOCK → WS-LIQ (capital release) and WS-INFRA → WS-PROFIT/WS-CASH (truth headline). Parallel from Phase 2 onward: up to 4 concurrent lanes (LINES/RETURNS/ADS/QUAR beside the critical path), each in its own worktree, DB writes serialized through the lease.

**Calendar estimate** (agent-executed, lanes parallel where the graph allows): Phase -1+0 ≈ 1–2 days · Phase 1 ≈ 1–2 days · Phase 2 ≈ 5–8 days (stock sequence + COGS backfill dominate) · Phase 3 ≈ 5–10 days (liquidation dwell windows are calendar-bound: T1 7d → T2 7–10d) · Phase 4 ≈ 3–5 days build + 30d observation windows (comeback rate, forecast) · Phase 5 ≈ 1 day. **Program to first full scoring: ~3 weeks; to 100% green incl. observation-window gates: ~6–7 weeks.** Dwell/observation windows, not agent work, dominate the tail.

## 4. Rollback map (RB-*) — referenced by every gate

| Ref | Area | Procedure |
|---|---|---|
| RB-GIT | Repo files | `git reset --hard <prechange_HEAD>` on the WS branch + restore untracked operational files from the Phase -1 manifest; never history-rewrite shared branches |
| RB-DB | app.db & WA DBs | Stop write jobs → restore from `sqlite3 .backup` artifact (incl. any -wal/-shm) → `PRAGMA integrity_check` → re-run freshness validators → restart jobs |
| RB-WORKBOOK | CRM/ActiveOrders/inbound/anchors | Restore by checksum+mtime from manifest; re-point symlink anchors only after verification |
| RB-PLIST | launchd | Restore prior plist from manifest; `launchctl bootout` + `bootstrap`; verify with `launchctl print` + heartbeat validator |
| RB-ENV | Env/secrets | Restore from private local backup; never print values; rotate if exposed (STOP-THE-LINE) |
| RB-PRICE | Price/upload files | Re-upload previous known-good file (staged per G-WA-02) — owner-notification batched, lane pauses if rollback uncertain |
| RB-ADS | Campaigns | Restore prior budgets/status from pre-change export; pause campaign if uncertain |
| RB-CASH-ANCHOR | Cash anchor | Compensating/reversal anchor through the documented cashflow process (REHEARSED in G-RDY-02); never silent edit |
| RB-STOCK-ANCHOR | Stock anchor | Governed supersession batch (REHEARSED in G-RDY-02); never stack anchors silently; worst case RB-DB |

## 5. Agent routing & concurrency

- **Orchestrator (Fable 5, this session lineage)**: decomposition, lease management, integration review (ACCEPT / ACCEPT_WITH_FOLLOWUP / REJECT_AND_REWORK / BLOCKED per packet return), phase-boundary heartbeats, deferred-queue triage, acceptance assembly. Holds final authority on every merge/apply.
- **Codex 5.5 x-high**: all precise backend lanes (table above) via `/goal` packets (in `starter_pack/`); each packet carries allowed/forbidden paths, write permission level, commands, acceptance criteria, stop conditions, return contract.
- **Fable 5 execution agents**: judgment lanes — floor economics (WS-PRICE), tranche economics (WS-LIQ), metric spec (WS-METRICS), COGS authority doc (WS-FX review), ambiguous quarantine rows (WS-QUAR).
- **Opus 4.8 review agents**: read-only adversarial review of every write diff before apply (backfills, anchors, count imports, residual settlement, tranche files); spec-conformance on packets' return contracts.
- **Forbidden**: two agents writing the same files; concurrent DB writes; concurrent scheduler mutations; any agent self-merging; any non-Fable agent making pricing/economics judgment calls.

## 6. Phase walkthrough (entry/exit)

- **Day 0 (pre-backup)**: WS-LINE31GUARD executes (external, reversible, OD-008). Owner session must already be recorded.
- **Phase -1**: enter with recorded YAML; exit when G-BCK-01..03 + G-ORD-04 green. Backup window per OD-023.
- **Phase 0**: exit when go/no-go table covers 100% of candidate writes (G-RDY-01), rehearsals pass (G-RDY-02), gating verified (G-RDY-03), lease protocol live (G-RDY-04), repo guards green (G-REPO-01/02).
- **Phase 1**: exit when all 8 jobs spawn clean (G-SCHED-01), forced-failure alert received (G-ALERT-01), heartbeat validator green (G-SCHED-03), supervised EOD applied per OD-015 (G-SCHED-02), offsite validated (G-BCK-04). G-SCHED-04 (strict gate → 0) begins converging here, completes during Phase 2.
- **Phase 2**: the big fan-out (table above). Exit = all 32 Phase-2 gates green. The stock sequence inside WS-STOCK is absolute: G-STOCK-01 → 02 → 03 → 04/05.
- **Phase 3**: business actions on restored truth. Exit = 16 gates green (dwell windows make this calendar-bound).
- **Phase 4**: structural loops. Exit = 6 gates green (30d observation windows).
- **Phase 5**: acceptance per the procedure in `GREEN_STATE_GATE_MATRIX.md` §6; final handoff per §7 below.

## 7. Final handoff (closeout artifact list — provenance-debt lens EXT-C06)

Executive status · what changed / intentionally not changed · command log (timestamps, exit codes, redacted env) · data before/after (table counts, max dates, coverage %, KZT exposures) · scored gate matrix · validation results · files changed · backup locations + manifest · rollback instructions (verified current) · deferred-queue final state · waiver list · remaining risks · owner decisions consumed (YAML hash) · recommended next program (PPCH v1 first publication review).

## 8. What this program does NOT do

No auto-PO restart (G-PO-01 keeps it governed-OFF; OD-009). No new purchasing decisions. No campaign scaling. No below-floor sales outside per-row exceptions (OD-032). No business-rule invention — every rule change traces to a recorded decision or an existing contract doc. No history rewrites, no external-system writes outside the approved envelopes (ads guard, relists, tranche uploads, campaign kill rule).
