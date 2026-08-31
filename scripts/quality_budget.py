# -*- coding: utf-8 -*-
"""Dependency-free structural quality metrics with a non-regression budget.

This is deliberately a ratchet, not a demand to remove all existing debt.  A
metric may improve below its checked-in baseline; it may not grow above it.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_DIRS = frozenset({
    ".git", ".github", ".pytest_cache", "__pycache__", "benchmarks", "data",
    "dist", "scripts", "tests", "verification",
})
FILE_LINES = 1000
FUNCTION_LINES = 150
COMPLEXITY = 20


def sources(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(
        path for path in root.rglob("*.py")
        if not any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts)
    ))


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
                              ast.ExceptHandler, ast.comprehension)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
        elif isinstance(child, ast.Match):
            score += max(0, len(child.cases) - 1)
    return score


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _local_imports(tree: ast.Module, local_roots: set[str]) -> set[str]:
    result: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level and node.module:
            # Relative imports are necessarily repository-local.  The first
            # component is sufficient for a stable coupling approximation.
            names = (node.module,)
        elif isinstance(node, ast.ImportFrom) and node.level and not node.module:
            names = (alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = (node.module,)
        else:
            continue
        for name in names:
            root = name.split(".", 1)[0]
            if node.level if isinstance(node, ast.ImportFrom) else root in local_roots:
                result.add(root)
    return result


def collect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = sources(root)
    local_roots = {path.relative_to(root).parts[0].removesuffix(".py") for path in paths}
    values: Counter[str] = Counter()
    maxima: Counter[str] = Counter()
    import_out: dict[str, int] = {}
    import_in: Counter[str] = Counter()
    top: dict[str, list[dict[str, Any]]] = {
        "files": [], "functions": [], "complexity": [], "sync_io": [], "broad_except": []
    }

    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise RuntimeError(f"cannot parse {relative}: {exc}") from exc
        line_count = len(text.splitlines())
        maxima["max_file_lines"] = max(maxima["max_file_lines"], line_count)
        if line_count >= FILE_LINES:
            values["giant_files"] += 1
            top["files"].append({"path": relative, "lines": line_count})

        module = _module_name(root, path)
        dependencies = _local_imports(tree, local_roots)
        import_out[module] = len(dependencies)
        import_in.update(dependencies)

        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                complexity = _complexity(node)
                maxima["max_function_lines"] = max(maxima["max_function_lines"], length)
                maxima["max_complexity"] = max(maxima["max_complexity"], complexity)
                if length >= FUNCTION_LINES:
                    values["giant_functions"] += 1
                    top["functions"].append({"path": relative, "line": node.lineno,
                                             "name": node.name, "lines": length})
                if complexity >= COMPLEXITY:
                    values["complex_functions"] += 1
                    top["complexity"].append({"path": relative, "line": node.lineno,
                                              "name": node.name, "complexity": complexity})
            elif isinstance(node, ast.ExceptHandler):
                caught = _name(node.type) if node.type else "bare"
                if caught in {"bare", "Exception", "BaseException"}:
                    values["broad_except"] += 1
                    top["broad_except"].append({"path": relative, "line": node.lineno,
                                                "caught": caught})
            elif isinstance(node, ast.ClassDef):
                base_count = len(node.bases)
                maxima["max_mro_bases"] = max(maxima["max_mro_bases"], base_count)
                if base_count > 1:
                    values["multiple_inheritance_classes"] += 1
            elif isinstance(node, ast.Call):
                called = _name(node.func)
                is_io = (called in {"open", "read_text", "read_bytes", "write_text", "write_bytes"}
                         or called.endswith(
                    (".open", ".read_text", ".read_bytes", ".write_text", ".write_bytes")
                ))
                if is_io:
                    values["sync_file_io_calls"] += 1
                    ancestor = parents.get(node)
                    in_async = False
                    while ancestor is not None:
                        if isinstance(ancestor, ast.AsyncFunctionDef):
                            in_async = True
                            break
                        if isinstance(ancestor, ast.FunctionDef):
                            break
                        ancestor = parents.get(ancestor)
                    if in_async:
                        values["sync_file_io_in_async"] += 1
                    top["sync_io"].append({"path": relative, "line": node.lineno,
                                           "call": called, "in_async": in_async})

    maxima["max_import_fan_out"] = max(import_out.values(), default=0)
    maxima["max_import_fan_in"] = max(import_in.values(), default=0)
    metrics = dict(sorted((values | maxima).items()))
    metrics["source_files"] = len(paths)
    for rows in top.values():
        rows.sort(key=lambda row: (-row.get("lines", row.get("complexity", 0)),
                                   row["path"], row.get("line", 0)))
    return {"version": 1, "thresholds": {"file_lines": FILE_LINES,
            "function_lines": FUNCTION_LINES, "complexity": COMPLEXITY},
            "metrics": metrics, "hotspots": top}


def compare(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if baseline.get("version") != report.get("version"):
        return ["baseline version does not match checker version"]
    actual = report["metrics"]
    budgets = baseline.get("budgets", {})
    for name, limit in sorted(budgets.items()):
        value = actual.get(name)
        if not isinstance(limit, int) or not isinstance(value, int):
            errors.append(f"invalid or unavailable metric {name!r}")
        elif value > limit:
            errors.append(f"{name}: {value} exceeds baseline budget {limit} (+{value-limit})")
    return errors


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--write-baseline", type=Path)
    args = parser.parse_args(argv)
    report = collect(args.root)
    if args.write_baseline:
        payload = {"version": report["version"], "budgets": report["metrics"]}
        args.write_baseline.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")
    errors: list[str] = []
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        errors = compare(report, baseline)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, value in report["metrics"].items():
            print(f"{name}: {value}")
    if errors:
        print("quality budget regressions:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print("quality budget passed" if args.baseline else "quality metrics collected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
