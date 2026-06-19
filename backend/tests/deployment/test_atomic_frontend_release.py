"""Tests for atomic frontend release activation and rollback."""

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "deployment" / "activate-frontend-release.sh"


def _make_release(frontend_root: Path, version: str, *, assets: bool = True) -> None:
    release = frontend_root / "releases" / version
    release.mkdir(parents=True)
    (release / "index.html").write_text(f"<html>{version}</html>")
    if assets:
        (release / "assets").mkdir()


def _run(frontend_root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "FRONTEND_ROOT": str(frontend_root)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_activation_migrates_legacy_dist_and_switches_symlink_atomically(tmp_path):
    frontend_root = tmp_path / "frontend"
    legacy_dist = frontend_root / "dist"
    legacy_dist.mkdir(parents=True)
    (legacy_dist / "index.html").write_text("legacy")
    _make_release(frontend_root, "v3.4.5")

    result = _run(frontend_root, "v3.4.5")

    assert result.returncode == 0, result.stderr
    assert (frontend_root / "dist").is_symlink()
    assert os.readlink(frontend_root / "dist") == "releases/v3.4.5"
    assert "legacy-" in (frontend_root / ".previous-frontend-release").read_text()


def test_rollback_switches_to_previous_release_and_records_current(tmp_path):
    frontend_root = tmp_path / "frontend"
    _make_release(frontend_root, "v3.4.4")
    _make_release(frontend_root, "v3.4.5")
    os.symlink("releases/v3.4.4", frontend_root / "dist")
    assert _run(frontend_root, "v3.4.5").returncode == 0

    result = _run(frontend_root, "--rollback")

    assert result.returncode == 0, result.stderr
    assert os.readlink(frontend_root / "dist") == "releases/v3.4.4"
    assert (frontend_root / ".previous-frontend-release").read_text().strip() == "releases/v3.4.5"


def test_activation_rejects_incomplete_artifact(tmp_path):
    frontend_root = tmp_path / "frontend"
    _make_release(frontend_root, "v3.4.5", assets=False)

    result = _run(frontend_root, "v3.4.5")

    assert result.returncode != 0
    assert "assets directory" in result.stderr
    assert not (frontend_root / "dist").exists()
