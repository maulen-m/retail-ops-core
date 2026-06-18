# Green Path Owner Action Starters

These are post-approval execution starters. Every agent must run the owner-action queue validator first:

```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/<agent-run-id>
```

If the assigned action status is still `WAITING_*`, close no-write.

After the owner supplies an approval/fact artifact, the orchestrator can record it with:

```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/record_owner_action_queue_status.py \
  --action-id OA-PRICE03-SUIT \
  --status APPROVED \
  --decision-artifact /absolute/path/to/approval.md \
  --note "owner exact approval" \
  --apply
```

The recorder is local-only, dry-run by default, and backs up the queue JSON/CSV before mutation.

Sequence:
1. Approval intake preflight.
2. ACMEWEAR compact SUIT/LINE price authority lane.
3. G-PRICE-05 Repricer disposition lane.
4. G-DARK-01 relist correction lane.
5. G-RET-02 real QC fact apply lane.
6. Cash source recheck lane, read-only and parallel-safe after 1.
