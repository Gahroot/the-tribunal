#!/usr/bin/env python3
"""Scan backend/app and produce a block-coupling report for authoring manifests.

Run from repo root:

    uv run python scripts/blocks/inventory.py

stdlib only. Parses every ``backend/app/**/*.py`` with :mod:`ast`, resolves each
``app.*`` import to the block that owns the target module's file, and reports for
each block: the files it owns, which other blocks it imports FROM, and the exact
cross-block import lines (``file:lineno: statement -> block``) that must be
severed to decouple the block.

Writes ``docs/blocks/coupling-report.json``.
"""

from __future__ import annotations

import ast
import fnmatch
import json
from collections import defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- #
# Block ownership map: block-id -> list of owned path globs.
#
# Globs are relative to the ``backend/`` directory (i.e. they start with
# ``app/``). They are intentionally aspirational: some target files/folders may
# not exist yet. Non-existent globs simply own nothing. When two blocks could
# claim the same file, the most-specific glob (longest literal prefix) wins.
# --------------------------------------------------------------------------- #
BLOCKS: dict[str, list[str]] = {
    "core": [
        "app/core/**",
        "app/db/**",
        "app/api/deps.py",
        "app/services/idempotency.py",
        "app/services/providers/**",
        "app/workers/base.py",
        "app/workers/runner.py",
        "app/workers/retryable.py",
    ],
    "widget": [
        # Extracted to backend/packages/widget/ (dist tribunal-widget, importable
        # as tribunal_widget). Only the back-compat shim remains in the app tree;
        # the live router/services live in the mounted block package.
        "app/api/v1/embed.py",
    ],
    "lead-capture": [
        # Extracted to backend/packages/lead-capture/ (dist tribunal-lead-capture,
        # importable as tribunal_lead_capture). Only the back-compat model/schema
        # shims remain in the app tree so app.models keeps re-exporting
        # LeadMagnet/LeadMagnetLead/LeadSource and Alembic still discovers the
        # tables; the live routers (lead_form/lead_magnets/lead_sources), the
        # delivery service, and the models live in the mounted block package.
        "app/models/lead_magnet.py",
        "app/models/lead_magnet_lead.py",
        "app/models/lead_source.py",
    ],
    "reviews": [
        # Extracted to backend/packages/reviews/ (dist tribunal-reviews, importable
        # as tribunal_reviews). Only the back-compat model/schema shims remain in
        # the app tree so app.models keeps re-exporting Review/ReviewRequest and
        # Alembic still discovers the tables; the live router/service/workers/AI
        # reply drafter live in the mounted block package.
        "app/models/review.py",
        "app/models/review_request.py",
    ],
    "offers": [
        "app/services/offers/**",
        "app/api/v1/offers.py",
        "app/models/offer.py",
        "app/models/offer_lead_magnet.py",
    ],
    "short-links": [
        # Extracted to backend/packages/short-links/ (dist tribunal-short-links,
        # importable as tribunal_short_links). Only the back-compat model shims
        # remain in the app tree so app.models keeps re-exporting ShortLink/
        # LinkClick and Alembic still discovers the tables; the live router/
        # service/models live in the mounted block package.
        "app/models/short_link.py",
        "app/models/link_click.py",
    ],
    "voice": [
        "app/services/calls/**",
        "app/services/telephony/**",
        "app/services/audio/**",
        "app/websockets/**",
        "app/api/v1/calls.py",
        "app/api/v1/voice_campaigns.py",
        "app/api/v1/roleplay.py",
    ],
    "messaging": [
        "app/services/messaging/**",
        "app/services/campaigns/**",
        "app/services/outbound/**",
        "app/api/v1/campaigns.py",
        "app/api/v1/drip_campaigns.py",
        "app/api/v1/outbound_missions.py",
    ],
    "appointments": [
        "app/services/appointments/**",
        "app/services/calendar/**",
        "app/api/v1/appointments.py",
        "app/api/v1/bookable_staff.py",
        "app/workers/reminder_worker.py",
    ],
    "payments": [
        "app/services/payments/**",
        "app/models/call_payment.py",
    ],
    "agent-brain": [
        "app/services/agents/**",
        "app/services/ai/**",
        "app/services/message_tests/**",
        "app/api/v1/agents.py",
        "app/api/v1/prompt_versions.py",
        "app/api/v1/message_tests.py",
        "app/api/v1/experiments/**",
    ],
    "hitl": [
        "app/services/approval/**",
        "app/services/nudges/**",
        "app/services/autonomy_mandate.py",
        "app/api/v1/pending_actions.py",
        "app/api/v1/nudges.py",
    ],
    "automations": [
        "app/services/automations/**",
        "app/api/v1/automations.py",
        "app/workers/automation_worker.py",
    ],
    "contacts": [
        "app/services/contacts/**",
        "app/services/segments/**",
        "app/services/tags/**",
        "app/api/v1/contacts.py",
        "app/api/v1/segments.py",
        "app/api/v1/tags.py",
    ],
    "knowledge": [
        "app/services/knowledge/**",
        "app/api/v1/knowledge_documents.py",
        "app/models/knowledge_chunk.py",
        "app/models/knowledge_document.py",
    ],
    "compliance": [
        "app/services/compliance/**",
        "app/services/rate_limiting/**",
        "app/models/opt_out.py",
    ],
}

UNASSIGNED = "unassigned"

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
APP_DIR = BACKEND_DIR / "app"
OUTPUT_PATH = REPO_ROOT / "docs" / "blocks" / "coupling-report.json"


def _glob_specificity(glob: str) -> int:
    """Longer literal (non-wildcard) prefix => more specific match."""
    literal = glob.split("*", 1)[0]
    return len(literal)


def owner_of(rel_path: str) -> str | None:
    """Return the block-id that owns ``rel_path`` (relative to backend/), or None.

    ``rel_path`` looks like ``app/services/calls/service.py``. The most specific
    matching glob wins so overlapping blocks resolve deterministically.
    """
    best_block: str | None = None
    best_score = -1
    for block, globs in BLOCKS.items():
        for glob in globs:
            if fnmatch.fnmatch(rel_path, glob):
                score = _glob_specificity(glob)
                if score > best_score:
                    best_score = score
                    best_block = block
    return best_block


def resolve_module(dotted: str) -> str | None:
    """Resolve a dotted ``app.*`` module to a backend-relative file path.

    Tries ``<parts>.py`` then ``<parts>/__init__.py``. Returns e.g.
    ``app/services/calls/service.py`` or None if no file exists.
    """
    if not dotted or dotted.split(".", 1)[0] != "app":
        return None
    parts = dotted.split(".")
    as_module = BACKEND_DIR.joinpath(*parts).with_suffix(".py")
    if as_module.is_file():
        return as_module.relative_to(BACKEND_DIR).as_posix()
    as_package = BACKEND_DIR.joinpath(*parts, "__init__.py")
    if as_package.is_file():
        return as_package.relative_to(BACKEND_DIR).as_posix()
    return None


def module_name_for(file_path: Path) -> str:
    """``backend/app/services/calls/foo.py`` -> ``app.services.calls.foo``."""
    rel = file_path.relative_to(BACKEND_DIR).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def absolute_dotted(module: str | None, level: int, current_module: str) -> str | None:
    """Resolve a possibly-relative import target to an absolute dotted name."""
    if level == 0:
        return module
    # Relative import: drop `level` trailing components from the current package.
    current_parts = current_module.split(".")
    # current_module is the module itself; its package is parts[:-1].
    base_parts = current_parts[:-1]
    if level > 1:
        base_parts = base_parts[: len(base_parts) - (level - 1)]
    if not base_parts:
        return module
    if module:
        return ".".join(base_parts + module.split("."))
    return ".".join(base_parts)


def statement_text(node: ast.AST) -> str:
    """Reconstruct a normalized import statement for human-readable output."""
    if isinstance(node, ast.Import):
        names = ", ".join(
            a.name + (f" as {a.asname}" if a.asname else "") for a in node.names
        )
        return f"import {names}"
    if isinstance(node, ast.ImportFrom):
        names = ", ".join(
            a.name + (f" as {a.asname}" if a.asname else "") for a in node.names
        )
        prefix = "." * (node.level or 0)
        return f"from {prefix}{node.module or ''} import {names}"
    return ""


def iter_import_targets(node: ast.AST, current_module: str):
    """Yield absolute dotted module names referenced by an import node.

    For ``from pkg import name`` we try ``pkg.name`` first (submodule) and fall
    back to ``pkg`` so ownership resolves at the finest granularity available.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
    elif isinstance(node, ast.ImportFrom):
        base = absolute_dotted(node.module, node.level or 0, current_module)
        if base is None:
            return
        for alias in node.names:
            candidate = f"{base}.{alias.name}"
            if resolve_module(candidate):
                yield candidate
            else:
                yield base


def main() -> int:
    if not APP_DIR.is_dir():
        raise SystemExit(f"backend app dir not found: {APP_DIR}")

    files_by_block: dict[str, list[str]] = defaultdict(list)
    depends_on: dict[str, set[str]] = defaultdict(set)
    cross_imports: dict[str, list[str]] = defaultdict(list)

    py_files = sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)

    for path in py_files:
        rel_backend = path.relative_to(BACKEND_DIR).as_posix()
        rel_repo = path.relative_to(REPO_ROOT).as_posix()
        owner = owner_of(rel_backend) or UNASSIGNED
        files_by_block[owner].append(rel_repo)

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"warn: could not parse {rel_repo}: {exc}")
            continue

        current_module = module_name_for(path)
        seen: set[tuple[str, int, str]] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            stmt = statement_text(node)
            for dotted in iter_import_targets(node, current_module):
                target_file = resolve_module(dotted)
                if target_file is None:
                    continue
                target_block = owner_of(target_file)
                if target_block is None or target_block == owner:
                    continue
                key = (rel_repo, node.lineno, target_block)
                if key in seen:
                    continue
                seen.add(key)
                depends_on[owner].add(target_block)
                cross_imports[owner].append(
                    f"{rel_repo}:{node.lineno}: {stmt}  -> {target_block}"
                )

    # Assemble report (include every declared block plus unassigned).
    all_blocks = list(BLOCKS.keys()) + [UNASSIGNED]
    report: dict[str, dict] = {}
    for block in all_blocks:
        report[block] = {
            "files": sorted(files_by_block.get(block, [])),
            "depends_on_blocks": sorted(depends_on.get(block, set())),
            "cross_imports": sorted(cross_imports.get(block, [])),
        }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Human-readable report.
    print("=" * 72)
    print("BLOCK COUPLING REPORT")
    print("=" * 72)
    for block in all_blocks:
        data = report[block]
        print()
        print(f"### {block}")
        print(f"  files owned: {len(data['files'])}")
        deps = data["depends_on_blocks"]
        print(f"  depends on blocks ({len(deps)}): {', '.join(deps) if deps else '-'}")
        xs = data["cross_imports"]
        print(f"  cross-block imports to sever ({len(xs)}):")
        for line in xs:
            print(f"    {line}")
    print()
    print("=" * 72)
    print(f"scanned {len(py_files)} files; wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
