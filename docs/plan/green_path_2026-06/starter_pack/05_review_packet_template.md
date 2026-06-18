# Opus review packet — template (instantiate per write-diff)

Dispatched by the orchestrator before every apply marked review-mandatory (PKT-PROFIT backfill, PKT-CASH anchor, PKT-STOCK ×3 steps, PKT-RESID, PKT-LIQ tranche files, PKT-POGOV tests) and any other diff the orchestrator wants attacked. Reviewer is READ-ONLY and adversarial.

---

Objective: ADVERSARIALLY review the proposed write before apply. Your default verdict is REJECT — the diff must earn ACCEPT.

Inputs (fill at dispatch):
- DIFF: <path to dry-run diff / row-level output>
- PACKET: <the dispatching packet id + its acceptance criteria>
- SCOPE: <the expected row/table/file scope + tolerance (±2% default per OD-015)>
- DECISIONS: ~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml (the relevant OD ids: <list>)
- GATES: the green_gates.csv rows this write claims to move: <list>
- BASELINE: the packet's re-baselined entry numbers (NOT the CN planning values)

Files to inspect: the diff; the script that produced it; the target table schemas (mode=ro); the packet's run log.
Files allowed to change: NONE. You are read-only.

Checks (all must pass for ACCEPT):
1. SCOPE: every changed row/file is inside the declared scope; count within tolerance of the re-baselined expectation; ZERO out-of-scope rows (one unexplained row = REJECT).
2. DECISION TRACE: the write is authorized by the named OD answers as recorded (not as the packet wishes); DEFER answers → fallback honored.
3. ORDERING: no sequencing invariant violated (INBOUND-before-count, backup-before-write, floor-before-tranche, dry-run-before-apply).
4. REVERSIBILITY: the rollback artifact for THIS write exists and is current (RB-* per plan §4); for anchors: the rehearsed procedure applies to this exact shape.
5. NON-CONTAMINATION: no secrets/PII in diff or logs; gross/net legs not merged; no business-rule change without its doc.
6. ARITHMETIC: re-add at least 3 aggregates in the diff from raw rows (avg×count derivations = automatic REJECT); units stated.
7. BLAST RADIUS: tables/files NOT in scope are untouched (spot-check counts before/after on 2 adjacent tables).
8. GATE HONESTY: the claimed gate movement matches the gate's `expected` exactly (not a weaker paraphrase).

Return contract (final message, no file writes):
VERDICT: ACCEPT | REJECT
- per-check PASS/FAIL with one line of evidence each
- for REJECT: the exact rows/criteria that failed + what a passing diff looks like
- residual risks even if ACCEPT (max 3, concrete)
