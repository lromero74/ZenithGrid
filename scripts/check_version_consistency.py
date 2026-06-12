#!/usr/bin/env python3
"""Validate release-version sources agree.

Checks:
- topmost CHANGELOG.md heading
- docs/architecture/index.json "version"
- latest git tag, unless --expected is supplied for pre-tag release prep
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^## \[(v\d+\.\d+\.\d+)\]", re.MULTILINE)


def read_changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise RuntimeError("Could not find top changelog version heading")
    return match.group(1)


def read_architecture_version() -> str:
    with (ROOT / "docs/architecture/index.json").open(encoding="utf-8") as fh:
        return json.load(fh)["version"]


def read_latest_tag() -> str:
    result = subprocess.run(
        ["git", "tag", "--sort=-version:refname"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not tags:
        raise RuntimeError("No git tags found")
    return tags[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected",
        help="Expected version during pre-tag release prep, e.g. v2.167.2",
    )
    args = parser.parse_args()

    versions = {
        "CHANGELOG.md": read_changelog_version(),
        "docs/architecture/index.json": read_architecture_version(),
    }
    if args.expected:
        versions["--expected"] = args.expected
    else:
        versions["latest git tag"] = read_latest_tag()

    unique = set(versions.values())
    if len(unique) != 1:
        print("Version mismatch:", file=sys.stderr)
        for source, version in versions.items():
            print(f"  {source}: {version}", file=sys.stderr)
        return 1

    version = unique.pop()
    print(f"Version sources agree: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
