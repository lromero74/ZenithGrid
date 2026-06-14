"""
Keeps the committed symbol-registry snapshot honest.

The snapshot (docs/symbol_registry.json) is a browsable map of every module
function and class method in backend/app, used to spot accidental duplicate
definitions before adding new code. Because it is generated, it can rot. These
tests re-derive it live (via the same ast scanner) and fail if the checked-in
file is stale — the fix is always:

    python scripts/symbol_registry.py --write

The scanner lives in scripts/ (shared tooling, not an importable package), so we
load it by file path the same way conftest loads migration helpers.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPO_ROOT / "scripts" / "symbol_registry.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("_symbol_registry", SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSymbolRegistrySnapshot:
    def test_scanner_exists(self):
        """Sanity: the tooling is where the docs/CLAUDE.md say it is."""
        assert SCANNER_PATH.exists(), f"missing {SCANNER_PATH}"

    def test_snapshot_is_current(self):
        """The committed snapshot must equal a fresh live scan."""
        scanner = _load_scanner()
        live = scanner._serialize(scanner.build_registry())
        snapshot = scanner.SNAPSHOT_PATH
        assert snapshot.exists(), (
            "Symbol registry snapshot missing — run: "
            "python scripts/symbol_registry.py --write"
        )
        assert snapshot.read_text(encoding="utf-8") == live, (
            "Symbol registry snapshot is STALE (a function was added, renamed, or "
            "removed without regenerating it). Run: "
            "python scripts/symbol_registry.py --write"
        )

    def test_find_definitions_locates_a_known_symbol(self):
        """The 'consult before adding' lookup actually finds real definitions."""
        scanner = _load_scanner()
        hits = scanner.find_definitions("get_quote_currency")
        # Defined as a module function (currency_utils) and as methods (Bot/Position).
        assert any(cls is None for _, cls, _ in hits)
        assert any(cls == "Position" for _, cls, _ in hits)

    def test_find_definitions_empty_for_unused_name(self):
        """A name that doesn't exist returns no hits (so it's safe to add)."""
        scanner = _load_scanner()
        assert scanner.find_definitions("definitely_not_a_real_symbol_xyz") == []
