from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "quality_budget", ROOT / "scripts" / "quality_budget.py"
)
assert SPEC and SPEC.loader
quality_budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality_budget)


class QualityBudgetTests(unittest.TestCase):
    def test_complexity_counts_decision_points(self) -> None:
        tree = ast.parse(
            "def sample(a, b):\n"
            "    if a and b:\n"
            "        for value in a:\n"
            "            try:\n"
            "                return value if value else None\n"
            "            except ValueError:\n"
            "                pass\n"
        )
        self.assertEqual(6, quality_budget._complexity(tree.body[0]))

    def test_collect_detects_each_debt_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.py"
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
            metrics = quality_budget.collect(root)["metrics"]
        self.assertEqual(1, metrics["giant_functions"])
        self.assertEqual(1, metrics["broad_except"])
        self.assertEqual(1, metrics["sync_file_io_calls"])
        self.assertEqual(1, metrics["sync_file_io_in_async"])
        self.assertEqual(1, metrics["multiple_inheritance_classes"])

    def test_baseline_is_a_non_regression_ratchet(self) -> None:
        report = {"version": 1, "metrics": {"broad_except": 4, "giant_files": 2}}
        self.assertEqual([], quality_budget.compare(
            report, {"version": 1, "budgets": {"broad_except": 4, "giant_files": 3}}
        ))
        self.assertEqual(
            ["broad_except: 4 exceeds baseline budget 3 (+1)"],
            quality_budget.compare(
                report, {"version": 1, "budgets": {"broad_except": 3}}
            ),
        )

    def test_checked_in_baseline_covers_reported_metrics(self) -> None:
        baseline = json.loads((ROOT / "quality-baseline.json").read_text(encoding="utf-8"))
        report = quality_budget.collect(ROOT)
        self.assertEqual([], quality_budget.compare(report, baseline))
        self.assertTrue({
            "giant_files", "giant_functions", "complex_functions", "broad_except",
            "sync_file_io_calls", "sync_file_io_in_async", "max_import_fan_in",
            "max_import_fan_out", "multiple_inheritance_classes", "max_mro_bases",
        }.issubset(baseline["budgets"]))


if __name__ == "__main__":
    unittest.main()
