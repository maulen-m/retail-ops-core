# Starter Pack — implementation launch surface

One prompt per execution agent, sequence/parallel metadata, copy-paste launch lines. **Nothing here launches until `OWNER_DECISIONS_RECORDED.yaml` is filled in the owner session.**

## Files

| File | Contents |
|---|---|
| `01_orchestrator_prompt.md` | The single master prompt for the implementation orchestrator (Fable 5). It consumes the program docs and dispatches everything below. |
| `02_packets_phase_neg1_0_1.md` | PKT-LINE31GUARD, PKT-BCK, PKT-READY, PKT-INFRA-SCHED, PKT-INFRA-ALERT |
| `03_packets_phase2.md` | PKT-LINES, PKT-PROFIT, PKT-FX, PKT-CASH, PKT-STOCK, PKT-RETURNS, PKT-ADS, PKT-QUAR, PKT-RESID |
| `04_packets_phase3_4_5.md` | PKT-PRICE, PKT-RELIST, PKT-LIQ, PKT-STOREFRONT, PKT-OPS, PKT-POGOV, PKT-METRICS, PKT-ACCEPT |
| `05_review_packet_template.md` | The Opus review packet (instantiated per write-diff) |

## Sequence / parallel metadata

```
DAY 0   PKT-LINE31GUARD                                  [orchestrator-executed, external, pre-backup]
P -1    PKT-BCK                                       [solo: holds BOTH write leases]
P 0     PKT-READY                                     [solo]
P 1     PKT-INFRA-SCHED ∥ PKT-INFRA-ALERT             [parallel: disjoint files; ALERT needs no DB lease]
P 2     PKT-STOCK (critical path, AB write lease)     [internal order absolute: INBOUND→counts→snapshot→clamps]
        ∥ PKT-LINES → PKT-QUAR                        [LINES feeds QUAR; AB lease passes between them]
        ∥ PKT-FX → PKT-CASH                           [FX feeds CASH]
        ∥ PKT-RETURNS ∥ PKT-ADS                       [independent]
        PKT-PROFIT after EOD live (PKT-INFRA-SCHED)   [largest backfill; Opus review mandatory]
        PKT-RESID any time after P0                   [S-effort, drains 132 strict-gate items]
        NOTE: AB-repo DB writes serialize through ONE lease regardless of lane parallelism —
        the orchestrator queues lease grants; read-only phases of each packet may overlap freely.
P 3     PKT-PRICE → PKT-LIQ                           [floor source before tranche pricing]
        ∥ PKT-RELIST ∥ PKT-STOREFRONT ∥ PKT-OPS       [independent, S-effort]
P 3→4   PKT-POGOV ∥ PKT-METRICS                       [after P2 lanes green]
P 5     PKT-ACCEPT                                    [solo; produces the scored matrix + handoff]
```

## Copy-paste launch lines

Implementation orchestrator (Claude Code, repo-write permissions, from the AB repo root):

```
cd ~/Docs/Autonomous_business && claude
# then paste the full contents of starter_pack/01_orchestrator_prompt.md
```

Codex lane (example — PKT-BCK; the orchestrator normally dispatches these itself via codex exec):

```
codex exec --cd ~/Docs/Autonomous_business - <<'EOF'
<paste the /goal packet PKT-BCK from 02_packets_phase_neg1_0_1.md>
EOF
```

Opus review lane (per diff, dispatched by the orchestrator): instantiate `05_review_packet_template.md`.

## Common packet rules (every packet below inherits these; they are part of each packet by reference)

1. **Program docs are the contract**: `_workspaces/2026-06-12_green_path/` — `MASTER_REMEDIATION_PLAN.md` (rules §1–2, rollback §4), `green_gates.csv` (your gates), `OWNER_DECISIONS_RECORDED.yaml` (decisions — consume ONLY this, never the pack prose), `reconciliation/canonical_numbers.csv` (planning numbers). Repo contracts override where stricter.
2. **Re-baseline at entry**: re-derive your input numbers read-only (`sqlite3 "file:...?mode=ro"`) before any write; record beside CN values in your run log.
3. **Write discipline**: dry-run → save row-level diff → check scope (±2% per OD-015) → Opus review where your packet says so → `--apply` under env gate. You hold the write lease ONLY while applying; release after.
4. **Stop conditions (universal)**: any STOP-THE-LINE trigger (plan §2.3) → halt lane, write `DEFERRED_QUEUE.md` entry, notify orchestrator. Unknown situation → ambiguity protocol (plan §2): policy table → park → continue elsewhere. NEVER contact the owner; NEVER reclassify red gates; NEVER write outside your allowed paths.
5. **Validation**: run your gate's verify_cmd(s) + the change-type gates (plan §1.7). Confirm validator semantics match gate intent first (plan §1.8).
6. **Return contract**: actions; files inspected/changed; commands + exit codes; validators run + results; gates moved (RED→GREEN w/ evidence); diffs; risks; rollback notes; deferred items; follow-ups. No secrets/PII anywhere.
7. **Protect the live pipeline**: after any scheduler/DB change, run `python3 scripts/validate_kaspi_order_sync_freshness.py` (G-ORD-04).
