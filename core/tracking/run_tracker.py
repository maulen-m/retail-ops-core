"""
Run Tracker for Recording Execution History

Part 3 requirement: Track run status/artifacts for run_end_of_day.py
and other batch jobs. Creates a "what happened last night" trail.

Usage:
    from core.tracking.run_tracker import RunTracker

    with RunTracker("END_OF_DAY", db_path) as run:
        run.start_step("ingest_sales")
        # ... do work ...
        run.complete_step(records=100)

        run.start_step("gen_dashboard")
        # ... do work ...
        run.complete_step(records=50)

    # Run is automatically completed when context exits
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import json


@dataclass
class RunStep:
    """Details of a single run step."""
    name: str
    order: int
    status: str = "PENDING"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    records_processed: int = 0
    error_message: Optional[str] = None
    notes: Optional[str] = None


class RunTracker:
    """
    Track execution of batch jobs with step-level detail.

    Writes to fact_runs and fact_run_steps tables for auditability.
    """

    def __init__(
        self,
        run_type: str,
        db_path: Optional[Path] = None,
        triggered_by: str = "MANUAL",
        environment: str = "PRODUCTION"
    ):
        """
        Initialize a run tracker.

        Args:
            run_type: Type of run ('END_OF_DAY', 'DASHBOARD', 'AUTO_PO', 'MANUAL')
            db_path: Path to database
            triggered_by: What triggered this run ('CRON', 'MANUAL', 'API')
            environment: Environment ('PRODUCTION', 'STAGING', 'DEV')
        """
        self.run_type = run_type
        self.db_path = db_path or Path(__file__).parent.parent.parent / "db" / "app.db"
        self.triggered_by = triggered_by
        self.environment = environment

        self.run_id: Optional[int] = None
        self.started_at: Optional[datetime] = None
        self.status = "PENDING"
        self.steps: list[RunStep] = []
        self.current_step: Optional[RunStep] = None
        self.step_order = 0

        # Metrics
        self.skus_processed = 0
        self.drafts_created = 0
        self.alerts_sent = 0
        self.errors_count = 0
        self.output_files: list[str] = []
        self.error_summary: list[str] = []

        # Fallback tracking
        self.fx_fallback_used = False
        self.demand_overrides_applied = 0
        self.guardrails_blocked = 0

    def __enter__(self):
        """Start the run when entering context."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Complete the run when exiting context."""
        if exc_type is not None:
            # Exception occurred
            self.fail(str(exc_val))
        elif self.errors_count > 0:
            self.partial()
        else:
            self.success()
        return False  # Don't suppress exceptions

    def _ensure_tables(self, conn: sqlite3.Connection):
        """Create tables if they don't exist."""
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT,
                duration_seconds REAL,
                steps_total INTEGER DEFAULT 0,
                steps_completed INTEGER DEFAULT 0,
                current_step TEXT,
                skus_processed INTEGER DEFAULT 0,
                drafts_created INTEGER DEFAULT 0,
                alerts_sent INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                fx_fallback_used INTEGER DEFAULT 0,
                demand_overrides_applied INTEGER DEFAULT 0,
                guardrails_blocked INTEGER DEFAULT 0,
                output_files TEXT,
                error_summary TEXT,
                notes TEXT,
                triggered_by TEXT,
                environment TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_run_steps (
                step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES fact_runs(run_id),
                step_name TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                duration_seconds REAL,
                records_processed INTEGER DEFAULT 0,
                error_message TEXT,
                notes TEXT
            )
        """)

        conn.commit()

    def start(self):
        """Start the run and create initial record."""
        self.started_at = datetime.now()
        self.status = "STARTED"

        conn = sqlite3.connect(str(self.db_path))
        self._ensure_tables(conn)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fact_runs (
                run_date, run_type, status, started_at, triggered_by, environment
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            date.today().isoformat(),
            self.run_type,
            self.status,
            self.started_at.isoformat(),
            self.triggered_by,
            self.environment
        ))

        self.run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self

    def start_step(self, step_name: str, notes: str = None):
        """Start a new step within the run."""
        # Complete previous step if any
        if self.current_step and self.current_step.status == "RUNNING":
            self.complete_step()

        self.step_order += 1
        step = RunStep(
            name=step_name,
            order=self.step_order,
            status="RUNNING",
            started_at=datetime.now().isoformat(),
            notes=notes
        )
        self.steps.append(step)
        self.current_step = step

        # Update DB
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fact_run_steps (
                run_id, step_name, step_order, status, started_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.run_id,
            step.name,
            step.order,
            step.status,
            step.started_at,
            step.notes
        ))

        cursor.execute("""
            UPDATE fact_runs
            SET current_step = ?, steps_total = ?
            WHERE run_id = ?
        """, (step.name, len(self.steps), self.run_id))

        conn.commit()
        conn.close()

    def complete_step(self, records: int = 0, notes: str = None):
        """Mark current step as completed."""
        if not self.current_step:
            return

        step = self.current_step
        step.status = "SUCCESS"
        step.completed_at = datetime.now().isoformat()
        step.records_processed = records
        if notes:
            step.notes = notes

        # Calculate duration
        started = datetime.fromisoformat(step.started_at)
        completed = datetime.fromisoformat(step.completed_at)
        duration = (completed - started).total_seconds()

        # Update DB
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE fact_run_steps
            SET status = ?, completed_at = ?, duration_seconds = ?,
                records_processed = ?, notes = ?
            WHERE run_id = ? AND step_name = ? AND step_order = ?
        """, (
            step.status,
            step.completed_at,
            duration,
            step.records_processed,
            step.notes,
            self.run_id,
            step.name,
            step.order
        ))

        cursor.execute("""
            UPDATE fact_runs
            SET steps_completed = ?
            WHERE run_id = ?
        """, (sum(1 for s in self.steps if s.status == "SUCCESS"), self.run_id))

        conn.commit()
        conn.close()

    def fail_step(self, error_message: str):
        """Mark current step as failed."""
        if not self.current_step:
            return

        step = self.current_step
        step.status = "FAILED"
        step.completed_at = datetime.now().isoformat()
        step.error_message = error_message
        self.errors_count += 1
        self.error_summary.append(f"{step.name}: {error_message}")

        # Update DB
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        started = datetime.fromisoformat(step.started_at) if step.started_at else datetime.now()
        completed = datetime.fromisoformat(step.completed_at)
        duration = (completed - started).total_seconds()

        cursor.execute("""
            UPDATE fact_run_steps
            SET status = ?, completed_at = ?, duration_seconds = ?, error_message = ?
            WHERE run_id = ? AND step_name = ? AND step_order = ?
        """, (
            step.status,
            step.completed_at,
            duration,
            step.error_message,
            self.run_id,
            step.name,
            step.order
        ))

        conn.commit()
        conn.close()

    def add_output_file(self, file_path: str):
        """Record an output file produced by this run."""
        self.output_files.append(file_path)

    def set_metrics(
        self,
        skus_processed: int = None,
        drafts_created: int = None,
        alerts_sent: int = None,
        fx_fallback: bool = None,
        overrides_applied: int = None,
        guardrails_blocked: int = None
    ):
        """Set run metrics."""
        if skus_processed is not None:
            self.skus_processed = skus_processed
        if drafts_created is not None:
            self.drafts_created = drafts_created
        if alerts_sent is not None:
            self.alerts_sent = alerts_sent
        if fx_fallback is not None:
            self.fx_fallback_used = fx_fallback
        if overrides_applied is not None:
            self.demand_overrides_applied = overrides_applied
        if guardrails_blocked is not None:
            self.guardrails_blocked = guardrails_blocked

    def _finalize(self, status: str, notes: str = None):
        """Finalize the run with given status."""
        self.status = status
        completed_at = datetime.now()
        duration = (completed_at - self.started_at).total_seconds() if self.started_at else 0

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE fact_runs
            SET status = ?,
                completed_at = ?,
                duration_seconds = ?,
                skus_processed = ?,
                drafts_created = ?,
                alerts_sent = ?,
                errors_count = ?,
                fx_fallback_used = ?,
                demand_overrides_applied = ?,
                guardrails_blocked = ?,
                output_files = ?,
                error_summary = ?,
                notes = ?
            WHERE run_id = ?
        """, (
            status,
            completed_at.isoformat(),
            duration,
            self.skus_processed,
            self.drafts_created,
            self.alerts_sent,
            self.errors_count,
            1 if self.fx_fallback_used else 0,
            self.demand_overrides_applied,
            self.guardrails_blocked,
            json.dumps(self.output_files) if self.output_files else None,
            "; ".join(self.error_summary) if self.error_summary else None,
            notes,
            self.run_id
        ))

        conn.commit()
        conn.close()

    def success(self, notes: str = None):
        """Mark run as successful."""
        self._finalize("SUCCESS", notes)

    def partial(self, notes: str = None):
        """Mark run as partially successful (some steps failed)."""
        self._finalize("PARTIAL", notes)

    def fail(self, error: str):
        """Mark run as failed."""
        self.error_summary.append(error)
        self._finalize("FAILED", error)

    def to_summary(self) -> dict:
        """Generate summary dict for logs/alerts."""
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "status": self.status,
            "duration_seconds": (datetime.now() - self.started_at).total_seconds() if self.started_at else 0,
            "steps_total": len(self.steps),
            "steps_completed": sum(1 for s in self.steps if s.status == "SUCCESS"),
            "skus_processed": self.skus_processed,
            "drafts_created": self.drafts_created,
            "errors_count": self.errors_count,
            "fx_fallback_used": self.fx_fallback_used,
            "demand_overrides_applied": self.demand_overrides_applied,
            "guardrails_blocked": self.guardrails_blocked,
            "output_files": self.output_files,
            "error_summary": self.error_summary,
        }


def get_last_run(run_type: str = None, db_path: Path = None) -> Optional[dict]:
    """Get the last run of a given type."""
    db_path = db_path or Path(__file__).parent.parent.parent / "db" / "app.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if run_type:
        cursor.execute("""
            SELECT * FROM fact_runs
            WHERE run_type = ?
            ORDER BY run_id DESC
            LIMIT 1
        """, (run_type,))
    else:
        cursor.execute("""
            SELECT * FROM fact_runs
            ORDER BY run_id DESC
            LIMIT 1
        """)

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_run_history(days: int = 7, db_path: Path = None) -> list[dict]:
    """Get run history for the last N days."""
    db_path = db_path or Path(__file__).parent.parent.parent / "db" / "app.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM fact_runs
        WHERE run_date >= date('now', ?)
        ORDER BY run_id DESC
    """, (f"-{days} days",))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
