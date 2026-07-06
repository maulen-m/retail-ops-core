import ast
from pathlib import Path


def test_dashboard_daily_column_checks_are_validate_only() -> None:
    source_path = Path(__file__).resolve().parents[1] / "scripts" / "update_cashflow_dashboard.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_daily_columns"
    ]

    assert len(calls) == 2
    for call in calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        assert isinstance(kwargs.get("allow_schema_write"), ast.Constant)
        assert kwargs["allow_schema_write"].value is False
