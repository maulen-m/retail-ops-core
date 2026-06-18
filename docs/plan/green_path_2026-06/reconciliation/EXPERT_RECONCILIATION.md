# Expert Answer Reconciliation — 2026-06-12

Inputs: external expert answer (`2026-06-11/231306_TASK-000_capital-efficiency-truth-decay-audit/Answer/External_expert_answer_12.06.2026_16_46_44.md`, 716 lines) × audit paper/register/sidecars × **live re-verification sweep run 2026-06-12 ~19:30 +05** (6 read-only agents V1–V6, sqlite `mode=ro`, zero writes to either repo).

Companion machine-readable artifacts (same directory):
- `canonical_numbers.csv` — 66 canonical claims (CN-001..066), ONE figure per claim with basis, confidence label, source rank, drift status. **All downstream program documents cite CN ids, never raw sources.**
- `dispositions.csv` — 86 dispositions: 17 INEF verdicts, 12 expert ODs, 35 extensions (EXT-*, incl. QA-1 recoveries EXT-M11 + EXT-A02), 10 residual risks (RISK-*), 6 expert defects (DEF-*), 6 paper asks (ASK-*).

## 1. Verdict on the expert answer

**Accept as the program spine, with 11 ACCEPT-WITH-MOD dispositions and 6 caught defects.** The expert confirmed 11/17 INEF entries and adjusted 6 — every adjustment converging toward the audit paper's own amended bands, and every number the expert recomputed from sidecars reproduced **exactly** against the live DB (V2–V4: frozen register to the tenge, leak 12,839 verbatim, ceiling 113,464 verbatim, backlog 103 exact, divergence 65,144,687.12 exact). Zero REFUTEs survive scrutiny in either direction. The expert's three genuinely new contributions — the Phase -1 backup mandate, the Owner Decision register format, and the metric/ladder/size-prior stack — are adopted as the spine of the remediation program.

The diagnostic layer is now **triple-validated**: audit blind verification (242→221/20/1) → expert sidecar reproduction → live re-derivation 2026-06-12.

## 2. The four buckets

1. **Confirmed diagnosis (11 INEF)** — recorded, no re-litigation. All still true live except where noted in §3.
2. **Adjustments (6)** — all adopted; each re-derived live before adoption (the expert had no DB; closing that loop was our half of the peer review). Notable: the expert's 1,387k tranche floor was **vindicated** (DEF-04) — the paper's 1,789,707 is now pinned (CN-033) and deprecated.
3. **Extensions (35 EXT rows)** — all adopted; 5 with modifications (backup method, ladder envelope language, validation-command rebuild, rollback rehearsal, tranche-1 redefinition). QA-1 recovered two items initially dropped: the 11th metric (exception age × KZT exposure, EXT-M11) and the single-write-orchestrator invariant (EXT-A02).
4. **Expert defects (6 DEF rows)** — caught, not inherited: garbled §12 command block; doc-mtime/authority conflation; OD register incompleteness (INEF-12 owner-gated with no OD row — the biggest one); the 1,789,707 flag (vindicated); phase-vocabulary collision; line-entries backfill window off by two weeks.

## 3. Post-audit drift report (what changed between 2026-06-11 and 2026-06-12)

The single most consequential output of the live sweep. Eight changes, three of which alter remediation scope:

| # | Change | Effect on program |
|---|---|---|
| 1 | **Line-entries writer SELF-REVIVED 2026-06-11** (+140 rows; June now 57.7% lineless, was 100%) — but 657 orders created 2026-05-15..06-04 have zero entries and were never backfilled or quarantined (CN-002, CN-021, CN-028) | INEF-10 reframed: *backfill the hole + restart status events (still dead, CN-003) + freshness guard* — not "revive the pipeline". Quarantine triage scope +657 orders (INEF-15). |
| 2 | **Second owner physical count exists** — 2026-06-04 "pre_shipments", 66 rows / 3,989 units, OWNER_APPROVED 2026-06-11 22:52, unimported (CN-016) | Count-import design now spans TWO approved counts; authority precedence is an explicit owner-protocol item (OD-004/021 merged). Owner is already count-engaged — the LINE51 extension ask is incremental, not novel. |
| 3 | **`/opt/homebrew/bin/python3` reappeared 2026-06-12 03:59** (brew python@3.14) — kaspi-marketing-hourly now spawns and dies on `ModuleNotFoundError: yaml`; 7 of 8 plists still exit 78; end-of-day's exit 78 was **never** interpreter-related (its .venv python 3.12.4 works) (CN-048, CN-049) | INEF-05 remediation respecified: repoint ALL jobs to a stable repo venv with pinned deps (not "the existing python3.13"); add a per-job EX_CONFIG diagnosis step; Telegram keys already exist in `.env` (CN-050) — alerting fix is env plumbing + forced-failure proof. |
| 4 | **Strict gate worsened**: 115 → 150 failure items in one day (+35/day on_delivery_freeze growth rate) (CN-051) | Quantifies urgency of WS-INFRA; degradation rate becomes a baseline metric. |
| 5 | **Campaign 2794142 logged its first conversion** 06-12 (8,490 GMV; June CRR 82.8% vs siblings 5.8–29.6%) (CN-046) | Kill rule must be CRR/contribution-threshold-based, not "zero-GMV" — the named-campaign framing is already stale. |
| 6 | **LINE31 2XL oversell deepened** — a 4th June order accepted 2026-06-11 21:40 onto a book-empty size (CN-056) | LINE31 spend cap/pause (OD-008/020) is the most time-sensitive business decision in D4. |
| 7 | COGS-legless completions 4,692 → 4,734 (+25/day); margin-blind window 18.40M → 18,853,031 KZT (+225k/day); June gross 2,649,998 all blind (CN-025/026/057) | The decay RATES are now measured — they price the cost of delay for the owner session. |
| 8 | Ad-hoc DB backup practice observed (`app.db.backup_romblik_live_orders_20260612_173304`, CN-059) + a live-but-failing operational-stock job (CN-058) | Phase -1 formalizes an existing habit; the green matrix must cover the op-stock job's 2,310 exceptions. |

Everything else is **byte-identical** to audit values (V1: 39 of 41 objects unchanged; V2: register exact; V3: all static legs exact; V4: all stale inputs byte-stable).

## 4. Definitions pinned (the two ambiguities that could have corrupted the program)

1. **Tranche-1** (CN-032/033): canonical = the 11-family / 1,003-unit intersection set (strict `u30=0` ∩ zero-COMPLETED), quoted on three explicit bases — **1,387,464 goods-only / 1,413,954 tiered / 1,704,105 waterfall-with-freight KZT** — all 11 families confirmed zero June movement. The paper's 1,789,707 = 12-family pre-06-11-status COMPLETED-only waterfall figure; real but deprecated (embeds a stale member, IVORY, which sold and exited).
2. **PPCH v0 portfolio yield** (CN-037): 18.92%/30d (capitalized rows only) vs 19.33% (including zero-capital-row GP). Program convention: **denominator-consistent (18.92%) for any yield statement**; the v1 spec must define the treatment explicitly.

## 5. What the merged program inherits

- **From the audit**: the register (with INEF-10/15 scope updates), the dependency graph (ratified by the expert on all 7 constraint judgments), the evidence/confidence vocabulary, the validator-backed verification culture.
- **From the expert**: Phase -1..5 as canonical phase vocabulary (EXT-R01); backup scope + stop-the-line triggers (EXT-B01/02); the 11-metric stack (EXT-M01..11); ladder + segmentation + gates (EXT-L01..06); size-prior spec (EXT-S01..03); 8 monitoring lenses (EXT-C01..08); per-change-type validation/rollback maps (EXT-V01/02, commands rebuilt from the live 130-script inventory, CN-053); the single-write-orchestrator invariant (EXT-A02); the OD register format, extended OD-001..012 → 30 decisions in D4.
- **From the live sweep**: every number with drift status; the re-baseline rule (planning numbers are for sizing — every workstream re-derives its inputs at execution start); the existing-assets list (CN-066: Telegram keys, tests/, backup habit, pre-Feb-13 working alerting) which shrinks the build scope.

## 6. Paper asks — all six adjudicated

ASK-1..5 fully answered (metric stack / ladder / size-curve / 8 classes / roadmap scored 6–9 + reordered). ASK-6 partially: the 113,464 UNVERIFIABLE SQA item is **closed** (arithmetic verified live, status = policy-contingent on v7 ratification, CN-040); INEF-07 trough adjustment and INEF-03 Feb COGS-ratio tightening were not delivered — both move to implementation telemetry (measured trough factor; measured comeback rate).

## 7. Gaps that survive reconciliation (carried into the program as work, not assumptions)

1. May seller-fee leg (59,668 KZT) of the ≈244,323 returns figure — UNVERIFIED; source query unrecorded (CN-017). WS-RETURNS re-derives at execution.
2. Dark-family listing state provable only via live offer fetch (DB offer table stale 2026-05-03) — WS-RELIST first step.
3. LINE31 "buyable" arithmetic rides the frozen ledger — physical truth unknowable until WS-STOCK unfreezes it (CN-056).
4. INEF-03 strict-window low bound (18,247,115) definition unrecorded — open-window basis (CN-026) is canonical going forward.
5. Audit paper §5.1/§8.3 tranche wording needs an annotation; the shipped paper stays frozen — the annotation lives HERE and in the master plan.
