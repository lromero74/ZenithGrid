#!/usr/bin/env python3
"""
Live symbol registry for the ZenithGrid backend.

Guards against accidentally adding a function/method that already exists. The
registry is built by parsing the source with Python's ``ast`` every time it
runs, so it can never drift from reality. A committed snapshot
(``docs/symbol_registry.json``) makes the symbol surface browsable and
diff-reviewable, and a test (``backend/tests/test_symbol_registry.py``) keeps
that snapshot honest by re-deriving it live and comparing.

Workflow — consult BEFORE adding a function:

    python scripts/symbol_registry.py --check get_account_portfolio
        → lists every place that name is already defined (file:line, class).

    python scripts/symbol_registry.py --duplicates
        → reports module-level function names defined in more than one file
          (the high-signal DRY smell — method names are often legitimately
          polymorphic, so they are reported separately).

    python scripts/symbol_registry.py --write
        → regenerate the snapshot after you intentionally add/rename/remove a
          function.

    python scripts/symbol_registry.py --verify
        → exit non-zero if the snapshot is stale (for CI / pre-commit).

Only top-level module functions and direct class methods are tracked — nested
helper closures are local and intentionally excluded.
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "backend" / "app"
SNAPSHOT_PATH = REPO_ROOT / "docs" / "symbol_registry.json"


def _iter_py_files(app_root):
    for path in sorted(app_root.rglob("*.py")):
        # __pycache__ never matches *.py; nothing else to exclude under app/.
        yield path


def _functions_in_body(body):
    """Names of FunctionDef/AsyncFunctionDef directly in a node body (not nested)."""
    return sorted(
        node.name
        for node in body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def build_registry(app_root=APP_ROOT):
    """Parse every app module and return {relpath: {functions, classes}}.

    Deterministic: keys and lists are sorted, so the JSON serialization is
    stable across runs and machines.
    """
    registry = {}
    for path in _iter_py_files(app_root):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        module_functions = _functions_in_body(tree.body)
        classes = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = _functions_in_body(node.body)
                if methods:
                    classes[node.name] = methods

        if module_functions or classes:
            registry[rel] = {"functions": module_functions, "classes": classes}
    return registry


def find_definitions(name, app_root=APP_ROOT):
    """Return [(relpath, class_or_None, lineno)] for every definition of ``name``."""
    hits = []
    for path in _iter_py_files(app_root):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                hits.append((rel, None, node.lineno))
            elif isinstance(node, ast.ClassDef):
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name == name:
                        hits.append((rel, node.name, method.lineno))
    return hits


def module_function_duplicates(registry=None):
    """Module-level function names defined in >1 file → {name: [files]}."""
    registry = registry if registry is not None else build_registry()
    locations = defaultdict(list)
    for rel, data in registry.items():
        for fn in data["functions"]:
            locations[fn].append(rel)
    return {fn: sorted(files) for fn, files in sorted(locations.items()) if len(files) > 1}


def method_duplicates(registry=None):
    """Method names defined across >1 class → {name: ["file::Class"]}. Often legit
    (interface/polymorphism); reported for awareness, not enforced."""
    registry = registry if registry is not None else build_registry()
    locations = defaultdict(list)
    for rel, data in registry.items():
        for cls, methods in data["classes"].items():
            for m in methods:
                locations[m].append(f"{rel}::{cls}")
    return {m: sorted(locs) for m, locs in sorted(locations.items()) if len(locs) > 1}


def _serialize(registry):
    return json.dumps(registry, indent=2, sort_keys=True) + "\n"


def cmd_write():
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(_serialize(build_registry()), encoding="utf-8")
    print(f"Wrote snapshot: {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")


def cmd_verify():
    current = _serialize(build_registry())
    if not SNAPSHOT_PATH.exists():
        print("Snapshot missing — run: python scripts/symbol_registry.py --write")
        return 1
    if SNAPSHOT_PATH.read_text(encoding="utf-8") != current:
        print("Snapshot is STALE — run: python scripts/symbol_registry.py --write")
        return 1
    print("Snapshot is current.")
    return 0


def cmd_check(name):
    hits = find_definitions(name)
    if not hits:
        print(f"'{name}' is not defined anywhere in backend/app — safe to add.")
        return 0
    print(f"'{name}' is already defined in {len(hits)} place(s):")
    for rel, cls, lineno in hits:
        where = f"{cls}." if cls else "(module) "
        print(f"  {rel}:{lineno}  {where}{name}")
    return 0


def cmd_duplicates():
    mod_dupes = module_function_duplicates()
    print(f"Module-level function names defined in >1 file ({len(mod_dupes)}):")
    if not mod_dupes:
        print("  (none)")
    for name, files in mod_dupes.items():
        print(f"  {name}: {', '.join(files)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live AST symbol registry for backend/app.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", metavar="NAME", help="Show where NAME is already defined.")
    group.add_argument("--duplicates", action="store_true", help="Report module-level dupes.")
    group.add_argument("--write", action="store_true", help="Regenerate the snapshot.")
    group.add_argument("--verify", action="store_true", help="Fail if snapshot is stale.")
    args = parser.parse_args(argv)

    if args.write:
        cmd_write()
        return 0
    if args.verify:
        return cmd_verify()
    if args.check:
        return cmd_check(args.check)
    if args.duplicates:
        return cmd_duplicates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
