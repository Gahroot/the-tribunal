#!/usr/bin/env python3
"""Scaffold a Level-3 standalone service block under ``services/<id>/``.

Usage (from the repo root)::

    python3 scripts/blocks/scaffold_service.py <block-id>
    # e.g. python3 scripts/blocks/scaffold_service.py voice

Clones ``services/_template/`` into ``services/<block-id>/``, substituting the
block id into package names, titles, config defaults, console-script names, and
docs. The result is a self-contained, bootable FastAPI service that the host CRM
calls over HTTP — see ``docs/blocks/SERVICE_BLOCK_PATTERN.md``.

It refuses to overwrite an existing service. The block id is validated as
kebab-case; if ``docs/blocks/registry.json`` is present it prints a note when the
id is not a known block (but does not refuse — services may be prototyped under
any id).

stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Repo layout anchors (this file lives at scripts/blocks/).
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SERVICES_DIR = REPO_ROOT / "services"
TEMPLATE_DIR = SERVICES_DIR / "_template"
REGISTRY_PATH = REPO_ROOT / "docs" / "blocks" / "registry.json"

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Sentinel tokens substituted throughout the template. ``__BLOCK_CLASS__`` is
# PascalCase (safe for identifiers); ``__BLOCK_TITLE__`` is Title Case (prose).
TOKEN_ID = "__BLOCK_ID__"
TOKEN_TITLE = "__BLOCK_TITLE__"
TOKEN_CLASS = "__BLOCK_CLASS__"
TOKEN_DESC = "__BLOCK_DESC__"


def fail(message: str) -> None:
    print(f"\u2716 {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_id(raw_id: str) -> str:
    block_id = raw_id.strip()
    if not KEBAB_RE.match(block_id):
        fail(
            f'Invalid block id "{block_id}". Use a kebab-case slug, e.g. "voice".'
        )
    return block_id


def check_registry(block_id: str) -> None:
    """Note (do not refuse) when the id is not a known block."""
    if not REGISTRY_PATH.is_file():
        return
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    entries = (
        registry.get("blocks", registry.get("nodes", []))
        if isinstance(registry, dict)
        else registry
    )
    ids = [b.get("id") for b in entries if isinstance(b, dict) and b.get("id")]
    if ids and block_id not in ids:
        print(
            f"! Note: \"{block_id}\" is not in docs/blocks/registry.json "
            f"(known: {', '.join(sorted(ids))}). Scaffolding anyway.",
            file=sys.stderr,
        )


def title_case(block_id: str) -> str:
    return " ".join(word.capitalize() for word in block_id.split("-"))


def pascal_case(block_id: str) -> str:
    return "".join(word.capitalize() for word in block_id.split("-"))


def render(template_text: str, substitutions: dict[str, str]) -> str:
    for token, value in substitutions.items():
        template_text = template_text.replace(token, value)
    return template_text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        fail("Usage: python3 scripts/blocks/scaffold_service.py <block-id>")

    block_id = validate_id(argv[1])
    check_registry(block_id)

    if not TEMPLATE_DIR.is_dir():
        fail(f"Template not found at {TEMPLATE_DIR} (services/_template/ missing).")

    target_dir = SERVICES_DIR / block_id
    if target_dir.exists():
        fail(f"services/{block_id}/ already exists — refusing to overwrite.")

    substitutions = {
        TOKEN_ID: block_id,
        TOKEN_TITLE: title_case(block_id),
        TOKEN_CLASS: pascal_case(block_id),
        TOKEN_DESC: f"Standalone Level-3 service for the {block_id} block.",
    }

    written = 0
    for src in sorted(TEMPLATE_DIR.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        dest = target_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Binary-safe copy for non-text (none today, but stay robust).
        try:
            text = src.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            dest.write_bytes(src.read_bytes())
            written += 1
            continue
        dest.write_text(render(text, substitutions), encoding="utf-8")
        written += 1

    rel_target = target_dir.relative_to(REPO_ROOT)
    print(f"\u2713 Created {rel_target}/ (tribunal-service-{block_id}, {written} files)")
    print("  Next:")
    print(f"    1. cd {rel_target} && uv sync")
    print(f"    2. Fill app/router.py with the {block_id} endpoints.")
    print("    3. Pick data ownership: call back to the host v1 API (default)")
    print("       or add a slice DB — see SERVICE_BLOCK_PATTERN.md §3.4.")
    print("    4. Set SERVICE_TOKEN_SECRET + HOST_API_URL; wire the host client.")
    print("    5. Generate the host client from /openapi.json; commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
