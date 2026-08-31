from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "quality_budget", ROOT / "scripts" / "quality_budget.py"
)
assert SPEC and SPEC.loader
quality_budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality_budget)


def test_complexity_counts_decision_points() -> None:
    tree = ast.parse(
        "def sample(a, b):\n"
        "    if a and b:\n"
        "        for value in a:\n"
        "            try:\n"
        "                return value if value else None\n"
        "            except ValueError:\n"
        "                pass\n"
    )
    function = tree.body[0]
    assert quality_budget._complexity(function) == 6


def test_collect_detects_each_debt_category(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    body = "\n".join("        value += 1" for _ in range(151))
    source.write_text(
        "from pathlib import Path\n"
        "class Mixed(First, Second):\n"
        "    pass\n"
        "async def hotspot(flag):\n"
        "    try:\n"
        "        Path('x').read_text()\n"
        "    except Exception:\n"
        "        pass\n"
        "    if flag:\n"
        "        value = 0\n"
        f"{body}\n"
        "    return value\n",
        encoding="utf-8",
    )
    report = quality_budget.collect(tmp_path)
    metrics = report["metrics"]
    assert metrics["giant_functions"] == 1
    assert metrics["broad_except"] == 1
    assert metrics["sync_file_io_calls"] == 1
    assert metrics["sync_file_io_in_async"] == 1
    assert metrics["multiple_inheritance_classes"] == 1


def test_baseline_is_a_non_regression_ratchet() -> None:
    report = {"version": 1, "metrics": {"broad_except": 4, "giant_files": 2}}
    assert quality_budget.compare(
        report, {"version": 1, "budgets": {"broad_except": 4, "giant_files": 3}}
    ) == []
    assert quality_budget.compare(
        report, {"version": 1, "budgets": {"broad_except": 3}}
    ) == ["broad_except: 4 exceeds baseline budget 3 (+1)"]


def test_checked_in_baseline_covers_reported_metrics() -> None:
    baseline = json.loads((ROOT / "quality-baseline.json").read_text(encoding="utf-8"))
    report = quality_budget.collect(ROOT)
    assert not quality_budget.compare(report, baseline)
    assert {
        "giant_files", "giant_functions", "complex_functions", "broad_except",
        "sync_file_io_calls", "sync_file_io_in_async", "max_import_fan_in",
        "max_import_fan_out", "multiple_inheritance_classes", "max_mro_bases",
    }.issubset(baseline["budgets"])
