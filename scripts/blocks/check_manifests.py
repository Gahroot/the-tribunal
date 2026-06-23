#!/usr/bin/env python3
"""CI guard that keeps the block registry honest.

Run from the repo root::

    python3 scripts/blocks/check_manifests.py

Fails with a non-zero exit code when:

* a known capability folder (from the ``BLOCKS`` block->paths map in
  ``scripts/blocks/inventory.py``) has no corresponding ``docs/blocks/<id>/BLOCK.md``, or
* ``docs/blocks/registry.json`` is out of date versus the manifests (it is
  regenerated in memory and byte-compared against the committed file), or
* ``docs/blocks/README.md`` is out of date versus the manifests.

This script never writes anything; it only reports drift. Run
``python3 scripts/blocks/build_registry.py`` and commit the result to fix it.

stdlib only.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sibling modules importable regardless of the caller's CWD.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_registry as registry  # noqa: E402
from inventory import BLOCKS  # noqa: E402

REPO_ROOT = registry.REPO_ROOT
BLOCKS_DIR = registry.BLOCKS_DIR


def check_capability_folders() -> list[str]:
    """Every block id in the inventory map must have a BLOCK.md manifest."""
    errors: list[str] = []
    for block_id in sorted(BLOCKS):
        manifest = BLOCKS_DIR / block_id / "BLOCK.md"
        if not manifest.is_file():
            errors.append(
                f"capability {block_id!r} has paths in scripts/blocks/inventory.py "
                f"but no manifest at {manifest.relative_to(REPO_ROOT)}"
            )
    return errors


def check_artifact(path: Path, expected: str, regen_hint: str) -> list[str]:
    if not path.is_file():
        return [
            f"{path.relative_to(REPO_ROOT)} is missing — run '{regen_hint}' and commit it"
        ]
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return [
            f"{path.relative_to(REPO_ROOT)} is out of date versus the manifests — "
            f"run '{regen_hint}' and commit it"
        ]
    return []


def main() -> int:
    errors: list[str] = []

    errors.extend(check_capability_folders())

    try:
        manifests = registry.load_manifests()
        cycles = registry.validate(manifests)
    except registry.ManifestError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    regen = "python3 scripts/blocks/build_registry.py"
    errors.extend(
        check_artifact(registry.REGISTRY_PATH, registry.registry_json(manifests), regen)
    )
    errors.extend(
        check_artifact(
            registry.README_PATH, registry.render_readme(manifests, cycles), regen
        )
    )

    if errors:
        print("✗ block manifest checks failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"✓ manifests in sync: {len(manifests)} blocks, "
        f"registry.json and README.md current"
    )
    if cycles:
        print(f"  ({len(cycles)} intentional dependency cycle(s) reported)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
