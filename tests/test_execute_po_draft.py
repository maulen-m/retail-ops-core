"""
Tests for Part 5: execute_po_draft.py

Tests execution safety requirements:
1. Execution blocked if any blocker exists
2. Only ORDER_FULL lines execute
3. Idempotency (safe to run twice without double execution)
"""

import os
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.execute_po_draft import (
    check_execution_gates,
    execute_po_draft,
    check_already_executed,
    revalidate_line_guardrails,
    write_reconciliation_csv,
    persist_reconciliation_artifact,
    ExecutionResult,
    # Part 7 functions
    get_daily_executed_spend,
    get_rollout_whitelist,
    check_rollout_caps,
    filter_by_whitelist,
    get_rollout_status,
)


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with required tables."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create fact_po_drafts table
    cursor.execute("""
        CREATE TABLE fact_po_drafts (
            draft_id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'PENDING',
            total_po_value_kzt REAL DEFAULT 0,
            total_order_qty INTEGER DEFAULT 0,
            skus_count INTEGER DEFAULT 0,
            roic_action_summary TEXT,
            guardrail_status TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        )
    """)

    # Create fact_po_draft_lines table
    cursor.execute("""
        CREATE TABLE fact_po_draft_lines (
            line_id INTEGER PRIMARY KEY,
            draft_id INTEGER,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            unit_cost_cny REAL,
            roic_pct REAL,
            current_stock INTEGER,
            rop INTEGER,
            d_forecast REAL
        )
    """)

    # Create fact_po_approvals table
    cursor.execute("""
        CREATE TABLE fact_po_approvals (
            approval_id INTEGER PRIMARY KEY,
            draft_id INTEGER,
            sku_key TEXT DEFAULT 'ALL',
            roic_action TEXT,
            approved_by TEXT,
            approved_at TEXT DEFAULT (datetime('now')),
            decision TEXT,
            notes TEXT,
            po_value_kzt REAL,
            order_qty INTEGER
        )
    """)

    # Create dim_sku table for costs
    cursor.execute("""
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL
        )
    """)

    # Create inventory snapshot table for capital preflight
    cursor.execute("""
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock INTEGER
        )
    """)

    # Insert test data
    # High ROIC SKU (ORDER_FULL)
    cursor.execute("""
        INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny)
        VALUES ('SKU_HIGH_ROIC', 5000, 50)
    """)

    # Low ROIC SKU (REVIEW_REQUIRED)
    cursor.execute("""
        INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny)
        VALUES ('SKU_LOW_ROIC', 5000, 50)
    """)

    # Inventory snapshot (latest)
    cursor.executemany(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-01-01", "SKU_HIGH_ROIC", 10),
            ("2026-01-01", "SKU_LOW_ROIC", 500),
        ],
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def draft_with_high_roic(test_db):
    """Create a draft with ORDER_FULL eligible lines."""
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO fact_po_drafts (draft_id, status, total_po_value_kzt)
        VALUES (1, 'PENDING', 500000)
    """)

    # High ROIC line (25% = ORDER_FULL)
    cursor.execute("""
        INSERT INTO fact_po_draft_lines
        (draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny, roic_pct)
        VALUES (1, 'SKU_HIGH_ROIC', 'SKU_HIGH_ROIC_M', 'M', 100, 50, 25)
    """)

    conn.commit()
    conn.close()

    return 1


@pytest.fixture
def draft_with_low_roic(test_db):
    """Create a draft with REVIEW_REQUIRED lines only."""
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO fact_po_drafts (draft_id, status, total_po_value_kzt)
        VALUES (2, 'PENDING', 500000)
    """)

    # Low ROIC line (5% = REVIEW_REQUIRED)
    cursor.execute("""
        INSERT INTO fact_po_draft_lines
        (draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny, roic_pct)
        VALUES (2, 'SKU_LOW_ROIC', 'SKU_LOW_ROIC_M', 'M', 100, 50, 5)
    """)

    conn.commit()
    conn.close()

    return 2


@pytest.fixture
def draft_mixed_roic(test_db):
    """Create a draft with mixed ROIC lines."""
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO fact_po_drafts (draft_id, status, total_po_value_kzt)
        VALUES (3, 'PENDING', 1000000)
    """)

    # High ROIC line (25% = ORDER_FULL)
    cursor.execute("""
        INSERT INTO fact_po_draft_lines
        (draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny, roic_pct)
        VALUES (3, 'SKU_HIGH_ROIC', 'SKU_HIGH_ROIC_M', 'M', 100, 50, 25)
    """)

    # Low ROIC line (5% = REVIEW_REQUIRED)
    cursor.execute("""
        INSERT INTO fact_po_draft_lines
        (draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny, roic_pct)
        VALUES (3, 'SKU_LOW_ROIC', 'SKU_LOW_ROIC_M', 'M', 100, 50, 5)
    """)

    conn.commit()
    conn.close()

    return 3


class TestExecutionGates:
    """Test env var safety gates."""

    def test_gates_disabled_by_default(self):
        """Verify execution is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Reimport to get fresh env var values
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_execution_gates()
            assert not can_execute
            assert len(blockers) >= 1

    def test_gates_block_without_all_three(self):
        """Verify ALL three gates must be enabled."""
        # Only AUTONOMOUS_PO_ENABLED
        with patch.dict(os.environ, {
            "AUTONOMOUS_PO_ENABLED": "true",
            "PO_DRAFT_ONLY": "true",
            "AUTO_EXECUTE_MODE": "DISABLED"
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_execution_gates()
            assert not can_execute
            assert len(blockers) >= 2  # PO_DRAFT_ONLY and AUTO_EXECUTE_MODE

    def test_gates_pass_with_all_three(self):
        """Verify execution allowed when all gates enabled."""
        with patch.dict(os.environ, {
            "AUTONOMOUS_PO_ENABLED": "true",
            "PO_DRAFT_ONLY": "false",
            "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY"
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_execution_gates()
            assert can_execute
            assert len(blockers) == 0

    def test_write_gate_requires_flag(self):
        """Verify PO_WRITE_ENABLED is required for live execution."""
        with patch.dict(os.environ, {
            "AUTONOMOUS_PO_ENABLED": "true",
            "PO_DRAFT_ONLY": "false",
            "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
            "PO_WRITE_ENABLED": "false",
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_execution_gates(require_write=True)
            assert not can_execute
            assert any("PO_WRITE_ENABLED" in b for b in blockers)


class TestBlockerBehavior:
    """Test that ANY blocker prevents execution."""

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
        "PO_WRITE_ENABLED": "true",
    })
    def test_low_roic_blocks_execution(self, test_db, draft_with_low_roic):
        """Verify low ROIC lines block execution."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        result = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_with_low_roic,
            dry_run=False
        )

        assert result.status == "BLOCKED"
        assert result.executed_lines == 0
        assert "No ORDER_FULL lines" in str(result.blockers) or result.blocked_lines > 0


class TestOrderFullOnly:
    """Test that ONLY ORDER_FULL lines execute."""

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
        "PO_WRITE_ENABLED": "true",
    })
    def test_only_high_roic_executes(self, test_db, draft_mixed_roic):
        """Verify only ORDER_FULL lines execute in mixed draft."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        result = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_mixed_roic,
            dry_run=True  # Dry run to check without side effects
        )

        # Should be DRY_RUN since gates are enabled
        assert result.status == "DRY_RUN"
        # Only the high ROIC line should execute
        assert result.executed_lines == 1
        # Low ROIC line should be skipped
        assert result.skipped_lines == 1

    def test_revalidate_filters_to_order_full(self, test_db):
        """Verify revalidation filters to ORDER_FULL only."""
        # Create test lines
        lines = [
            {"sku_key": "SKU_HIGH_ROIC", "quantity": 100, "roic_pct": 25},
            {"sku_key": "SKU_LOW_ROIC", "quantity": 100, "roic_pct": 5},
        ]

        order_full, blocked, blockers = revalidate_line_guardrails(test_db, lines)

        # Only high ROIC should pass
        assert len(order_full) == 1
        assert order_full[0]["sku_key"] == "SKU_HIGH_ROIC"

        # Low ROIC should be blocked
        assert len(blocked) == 1
        assert blocked[0]["sku_key"] == "SKU_LOW_ROIC"


class TestIdempotency:
    """Test idempotency (safe to run twice)."""

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
        "PO_WRITE_ENABLED": "true",
    })
    def test_second_execution_returns_idempotent(self, test_db, draft_with_high_roic):
        """Verify second execution returns IDEMPOTENT status."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        # First execution
        result1 = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_with_high_roic,
            dry_run=False
        )

        # Should succeed
        assert result1.status == "SUCCESS"
        assert result1.execution_id is not None

        # Second execution
        result2 = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_with_high_roic,
            dry_run=False
        )

        # Should return IDEMPOTENT, not execute again
        assert result2.status == "IDEMPOTENT"
        assert result2.executed_lines == 0

    def test_already_executed_check(self, test_db, draft_with_high_roic):
        """Verify check_already_executed works correctly."""
        # Initially not executed
        assert not check_already_executed(test_db, draft_with_high_roic)

        # Create execution record
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_po_executions (
                execution_id INTEGER PRIMARY KEY,
                draft_id INTEGER,
                status TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO fact_po_executions (draft_id, status)
            VALUES (?, 'SUCCESS')
        """, (draft_with_high_roic,))
        conn.commit()
        conn.close()

        # Now should be detected as executed
        assert check_already_executed(test_db, draft_with_high_roic)


class TestExecutionDisabled:
    """Test behavior when execution is disabled."""

    def test_returns_disabled_when_gates_closed(self, test_db, draft_with_high_roic):
        """Verify DISABLED status when gates are closed."""
        with patch.dict(os.environ, {
            "AUTONOMOUS_PO_ENABLED": "false",
            "PO_DRAFT_ONLY": "true",
            "AUTO_EXECUTE_MODE": "DISABLED"
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            result = epd.execute_po_draft(
                db_path=test_db,
                draft_id=draft_with_high_roic,
                dry_run=False
            )

            assert result.status == "DISABLED"
            assert result.executed_lines == 0
            assert len(result.blockers) > 0


class TestDryRun:
    """Test dry-run mode."""

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY"
    })
    def test_dry_run_no_side_effects(self, test_db, draft_with_high_roic):
        """Verify dry-run doesn't modify database."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        # Get initial draft status
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM fact_po_drafts WHERE draft_id = ?",
                      (draft_with_high_roic,))
        initial_status = cursor.fetchone()[0]
        conn.close()

        # Run dry-run
        result = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_with_high_roic,
            dry_run=True
        )

        assert result.status == "DRY_RUN"

        # Verify draft status unchanged
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM fact_po_drafts WHERE draft_id = ?",
                      (draft_with_high_roic,))
        final_status = cursor.fetchone()[0]
        conn.close()

        assert final_status == initial_status

        # Verify no execution record created
        assert not check_already_executed(test_db, draft_with_high_roic)


class TestReconciliationArtifact:
    """Part 6: Test reconciliation artifact generation."""

    def test_write_reconciliation_csv(self, tmp_path):
        """Verify reconciliation CSV is generated with correct structure."""
        result = ExecutionResult(
            draft_id=123,
            status="SUCCESS",
            executed_lines=2,
            skipped_lines=1,
            blocked_lines=0,
            total_value_kzt=500000,
            draft_value_kzt=750000,
            execution_id=456,
        )
        result.executed_sku_details = [
            {"sku_key": "SKU_A", "sku_id": "SKU_A_M", "my_size": "M", "quantity": 50, "value_kzt": 250000, "roic_pct": 25},
            {"sku_key": "SKU_B", "sku_id": "SKU_B_L", "my_size": "L", "quantity": 50, "value_kzt": 250000, "roic_pct": 22},
        ]
        result.skipped_sku_details = [
            {"sku_key": "SKU_C", "sku_id": "SKU_C_XL", "my_size": "XL", "quantity": 50, "value_kzt": 250000, "roic_pct": 8, "reason": "LOW_ROIC"},
        ]

        output_path = write_reconciliation_csv(result, tmp_path)

        assert output_path is not None
        assert output_path.exists()
        assert "execution_reconciliation" in output_path.name

        # Read and verify content
        content = output_path.read_text()
        assert "EXECUTION RECONCILIATION" in content
        assert "Draft #123" in content
        assert "SUCCESS" in content
        assert "EXECUTED LINES" in content
        assert "SKIPPED LINES" in content
        assert "SKU_A" in content
        assert "SKU_C" in content
        assert "LOW_ROIC" in content

    def test_reconciliation_csv_includes_all_sections(self, tmp_path):
        """Verify all required sections are present in reconciliation CSV."""
        result = ExecutionResult(
            draft_id=1,
            status="BLOCKED",
            blockers=["Missing cost data", "Budget exceeded"],
        )

        output_path = write_reconciliation_csv(result, tmp_path)

        assert output_path is not None
        content = output_path.read_text()

        # Check summary section
        assert "SUMMARY" in content
        assert "Draft ID" in content
        assert "Execution Status" in content
        assert "Idempotency Status" in content

        # Check blockers section
        assert "BLOCKERS" in content
        assert "Missing cost data" in content
        assert "Budget exceeded" in content

    def test_reconciliation_shows_execution_rate(self, tmp_path):
        """Verify execution rate is calculated correctly."""
        result = ExecutionResult(
            draft_id=1,
            status="SUCCESS",
            executed_lines=1,
            total_value_kzt=500000,
            draft_value_kzt=1000000,
        )

        output_path = write_reconciliation_csv(result, tmp_path)
        content = output_path.read_text()

        # 50% execution rate
        assert "50.0%" in content

    def test_persist_reconciliation_artifact(self, test_db):
        """Verify artifact path is persisted to fact_run_steps."""
        # Create fact_run_steps table
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_run_steps (
                step_id INTEGER PRIMARY KEY,
                run_id INTEGER,
                step_name TEXT,
                step_order INTEGER,
                status TEXT,
                started_at TEXT,
                completed_at TEXT,
                output_file TEXT,
                notes TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Persist artifact
        result = persist_reconciliation_artifact(
            test_db, run_id=42, artifact_path=Path("/exports/recon.csv")
        )

        assert result is True

        # Verify in database
        conn = sqlite3.connect(str(test_db))
        row = conn.execute(
            "SELECT * FROM fact_run_steps WHERE run_id = 42"
        ).fetchone()
        conn.close()

        assert row is not None
        assert "execution_reconciliation" in row[2]  # step_name
        assert "/exports/recon.csv" in row[7]  # output_file

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY"
    })
    def test_execution_creates_reconciliation_artifact(self, test_db, draft_with_high_roic, tmp_path):
        """Verify successful execution creates reconciliation artifact."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        # Monkey-patch EXPORTS_DIR for this test
        original_exports = epd.EXPORTS_DIR
        epd.EXPORTS_DIR = tmp_path

        try:
            result = epd.execute_po_draft(
                db_path=test_db,
                draft_id=draft_with_high_roic,
                dry_run=False
            )

            assert result.status == "SUCCESS"
            assert result.reconciliation_path is not None
            assert Path(result.reconciliation_path).exists()
        finally:
            epd.EXPORTS_DIR = original_exports


class TestPart7RolloutCaps:
    """Part 7: Test rollout spend caps."""

    def test_get_daily_executed_spend_empty(self, test_db):
        """Test daily spend is 0 when no executions."""
        spend = get_daily_executed_spend(test_db)
        assert spend == 0.0

    def test_get_daily_executed_spend_with_executions(self, test_db):
        """Test daily spend calculation."""
        from datetime import date

        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Create executions table and add data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_po_executions (
                execution_id INTEGER PRIMARY KEY,
                draft_id INTEGER,
                executed_at TEXT,
                status TEXT,
                total_value_kzt REAL
            )
        """)

        today = date.today().isoformat()
        cursor.execute("""
            INSERT INTO fact_po_executions (draft_id, executed_at, status, total_value_kzt)
            VALUES (1, ?, 'SUCCESS', 500000)
        """, (today + " 10:00:00",))
        cursor.execute("""
            INSERT INTO fact_po_executions (draft_id, executed_at, status, total_value_kzt)
            VALUES (2, ?, 'SUCCESS', 300000)
        """, (today + " 12:00:00",))
        # Add a BLOCKED execution (should not count)
        cursor.execute("""
            INSERT INTO fact_po_executions (draft_id, executed_at, status, total_value_kzt)
            VALUES (3, ?, 'BLOCKED', 200000)
        """, (today + " 14:00:00",))

        conn.commit()
        conn.close()

        spend = get_daily_executed_spend(test_db)
        assert spend == 800000.0  # Only SUCCESS executions count

    def test_check_rollout_caps_no_caps(self, test_db):
        """Test that no caps = no blocking."""
        with patch.dict(os.environ, {
            "MAX_EXECUTE_SPEND_PER_DAY_KZT": "0",
            "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "0",
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_rollout_caps(test_db, 10000000)
            assert can_execute
            assert len(blockers) == 0

    def test_check_rollout_caps_draft_cap_exceeded(self, test_db):
        """Test draft cap blocks execution."""
        with patch.dict(os.environ, {
            "MAX_EXECUTE_SPEND_PER_DAY_KZT": "0",
            "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "500000",
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            can_execute, blockers = epd.check_rollout_caps(test_db, 600000)
            assert not can_execute
            assert len(blockers) == 1
            assert "MAX_EXECUTE_SPEND_PER_DRAFT_KZT" in blockers[0]

    def test_check_rollout_caps_daily_cap_exceeded(self, test_db):
        """Test daily cap blocks execution after previous executions."""
        from datetime import date

        # Add prior execution
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_po_executions (
                execution_id INTEGER PRIMARY KEY,
                draft_id INTEGER,
                executed_at TEXT,
                status TEXT,
                total_value_kzt REAL
            )
        """)
        today = date.today().isoformat()
        cursor.execute("""
            INSERT INTO fact_po_executions (draft_id, executed_at, status, total_value_kzt)
            VALUES (1, ?, 'SUCCESS', 800000)
        """, (today + " 10:00:00",))
        conn.commit()
        conn.close()

        with patch.dict(os.environ, {
            "MAX_EXECUTE_SPEND_PER_DAY_KZT": "1000000",
            "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "0",
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            # Try to spend 300000 more (would exceed 1M cap)
            can_execute, blockers = epd.check_rollout_caps(test_db, 300000)
            assert not can_execute
            assert len(blockers) == 1
            assert "Daily cap" in blockers[0]


class TestPart7WhitelistFiltering:
    """Part 7: Test SKU whitelist filtering."""

    def test_filter_by_whitelist_no_whitelist(self):
        """Test no filtering when whitelist is empty."""
        lines = [
            {"sku_key": "SKU_A", "quantity": 10},
            {"sku_key": "SKU_B", "quantity": 20},
        ]

        passed, filtered = filter_by_whitelist(lines, set())
        assert len(passed) == 2
        assert len(filtered) == 0

    def test_filter_by_whitelist_with_whitelist(self):
        """Test filtering with active whitelist."""
        lines = [
            {"sku_key": "SKU_A", "quantity": 10},
            {"sku_key": "SKU_B", "quantity": 20},
            {"sku_key": "SKU_C", "quantity": 30},
        ]

        whitelist = {"SKU_A", "SKU_C"}
        passed, filtered = filter_by_whitelist(lines, whitelist)

        assert len(passed) == 2
        assert len(filtered) == 1
        assert passed[0]["sku_key"] == "SKU_A"
        assert passed[1]["sku_key"] == "SKU_C"
        assert filtered[0]["sku_key"] == "SKU_B"

    def test_get_rollout_whitelist_from_file(self, tmp_path, test_db):
        """Test loading whitelist from file."""
        whitelist_file = tmp_path / "whitelist.txt"
        whitelist_file.write_text("SKU_ONE\nSKU_TWO\n# This is a comment\nSKU_THREE\n")

        with patch.dict(os.environ, {
            "ROLLOUT_SKU_WHITELIST_PATH": str(whitelist_file),
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            whitelist = epd.get_rollout_whitelist(test_db)
            assert len(whitelist) == 3
            assert "SKU_ONE" in whitelist
            assert "SKU_TWO" in whitelist
            assert "SKU_THREE" in whitelist
            assert "# This is a comment" not in whitelist

    def test_get_rollout_whitelist_from_database(self, test_db):
        """Test loading whitelist from dim_rollout_whitelist table."""
        with patch.dict(os.environ, {"ROLLOUT_SKU_WHITELIST_PATH": ""}):
            # Create table and add data
            conn = sqlite3.connect(str(test_db))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE dim_rollout_whitelist (
                    sku_key TEXT PRIMARY KEY,
                    active_flag INTEGER DEFAULT 1
                )
            """)
            cursor.execute("INSERT INTO dim_rollout_whitelist VALUES ('DB_SKU_1', 1)")
            cursor.execute("INSERT INTO dim_rollout_whitelist VALUES ('DB_SKU_2', 1)")
            cursor.execute("INSERT INTO dim_rollout_whitelist VALUES ('DB_SKU_INACTIVE', 0)")
            conn.commit()
            conn.close()

            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            whitelist = epd.get_rollout_whitelist(test_db)
            assert len(whitelist) == 2
            assert "DB_SKU_1" in whitelist
            assert "DB_SKU_2" in whitelist
            assert "DB_SKU_INACTIVE" not in whitelist

    def test_get_rollout_status(self, test_db):
        """Test rollout status summary."""
        with patch.dict(os.environ, {
            "MAX_EXECUTE_SPEND_PER_DAY_KZT": "1000000",
            "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "500000",
            "ROLLOUT_SKU_WHITELIST_PATH": "",
        }):
            import importlib
            import scripts.execute_po_draft as epd
            importlib.reload(epd)

            status = epd.get_rollout_status(test_db)

            assert status["caps_enabled"] is True
            assert status["daily_cap_kzt"] == 1000000
            assert status["draft_cap_kzt"] == 500000
            assert status["daily_executed_kzt"] == 0.0
            assert status["daily_remaining_kzt"] == 1000000.0
            assert status["whitelist_enabled"] is False


class TestPart7ExecutionWithCaps:
    """Part 7: Test execution with rollout caps active."""

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
        "PO_WRITE_ENABLED": "true",
        "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "100000",  # Very low cap
    })
    def test_execution_blocked_by_draft_cap(self, test_db, draft_with_high_roic):
        """Test execution blocked when draft cap exceeded."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        result = epd.execute_po_draft(
            db_path=test_db,
            draft_id=draft_with_high_roic,
            dry_run=False
        )

        # High ROIC draft is 500000 KZT, cap is 100000
        assert result.status == "BLOCKED"
        assert result.cap_blocked is True
        assert any("MAX_EXECUTE_SPEND_PER_DRAFT_KZT" in b for b in result.blockers)

    @patch.dict(os.environ, {
        "AUTONOMOUS_PO_ENABLED": "true",
        "PO_DRAFT_ONLY": "false",
        "AUTO_EXECUTE_MODE": "ORDER_FULL_ONLY",
        "PO_WRITE_ENABLED": "true",
        "MAX_EXECUTE_SPEND_PER_DRAFT_KZT": "0",
        "MAX_EXECUTE_SPEND_PER_DAY_KZT": "0",
    })
    def test_execution_succeeds_with_no_caps(self, test_db, draft_with_high_roic, tmp_path):
        """Test execution succeeds when no caps configured."""
        import importlib
        import scripts.execute_po_draft as epd
        importlib.reload(epd)

        # Monkey-patch EXPORTS_DIR for this test
        original_exports = epd.EXPORTS_DIR
        epd.EXPORTS_DIR = tmp_path

        try:
            result = epd.execute_po_draft(
                db_path=test_db,
                draft_id=draft_with_high_roic,
                dry_run=False
            )

            assert result.status == "SUCCESS"
            assert result.cap_blocked is False
        finally:
            epd.EXPORTS_DIR = original_exports


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
