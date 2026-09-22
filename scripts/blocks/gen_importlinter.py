#!/usr/bin/env python3
"""Generate ``backend/.importlinter`` from the block registry + inventory path map.

Run from the repo root::

    python3 scripts/blocks/gen_importlinter.py            # regenerate everything
    python3 scripts/blocks/gen_importlinter.py --config-only  # skip lint-imports run

The block architecture is documented in two places that this script reads:

* ``docs/blocks/registry.json`` — each block's ``depends_on`` (the *only* sibling
  blocks it is allowed to import from), and
* the ``BLOCKS`` path map in :mod:`scripts.blocks.inventory` — which backend
  modules each block owns.

From those two sources it emits one ``forbidden`` Import Linter contract per
block that forbids the block's modules from importing any *sibling* block that is
NOT in its declared ``depends_on``, plus a "core independence" contract asserting
the core substrate (``app.core``, ``app.db``, ``app.api.deps``) imports no feature
block. Every block is always allowed to import ``app.core_api`` (the facade),
``app.core``, ``app.db`` and ``app.models`` — those are never placed in any
``forbidden_modules`` set.

After writing the config it runs ``lint-imports`` to discover which contracts the
*current* codebase already satisfies. The clean contracts (always including core
independence, which must stay clean) are written to
``backend/.importlinter-enforced`` — the subset wired into ``make ci.backend``.
The contracts that still fail, plus their offending imports, are written to
``docs/blocks/boundary-violations.md`` as the decoupling worklist.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from inventory import BLOCKS  # noqa: E402  (path injected above)

REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
REGISTRY_PATH = REPO_ROOT / "docs" / "blocks" / "registry.json"
CONFIG_PATH = BACKEND_DIR / ".importlinter"
ENFORCED_PATH = BACKEND_DIR / ".importlinter-enforced"
VIOLATIONS_PATH = REPO_ROOT / "docs" / "blocks" / "boundary-violations.md"

CORE_BLOCK = "core"

# Module prefixes every block may always import, so they are never forbidden:
#   - app.core / app.db        the core substrate's public internals
#   - app.api.deps             DI/auth dependencies (part of core)
#   - app.core_api             the canonical facade re-exporting core
#   - app.models               the shared ORM/data layer
ALWAYS_ALLOWED_PREFIXES = (
    "app.core_api",
    "app.models",
)


def glob_to_module(glob: str) -> str | None:
    """Resolve a ``BLOCKS`` path glob to an existing dotted module, or ``None``.

    ``app/services/calls/**`` -> ``app.services.calls`` (package dir must exist).
    ``app/api/v1/calls.py``   -> ``app.api.v1.calls`` (file must exist).
    Globs whose target does not exist on disk (aspirational paths) return None.
    """
    g = glob.rstrip("/")
    for suffix in ("/**", "/*"):
        if g.endswith(suffix):
            g = g[: -len(suffix)]
            break
    if g.endswith(".py"):
        g = g[:-3]
    parts = [p for p in g.split("/") if p]
    if not parts or parts[0] != "app":
        return None
    as_file = BACKEND_DIR.joinpath(*parts).with_suffix(".py")
    as_pkg = BACKEND_DIR.joinpath(*parts)
    if as_file.is_file() or as_pkg.is_dir():
        return ".".join(parts)
    return None


def _is_model(module: str) -> bool:
    return module == "app.models" or module.startswith("app.models.")


def resolve_block_modules() -> dict[str, list[str]]:
    """block-id -> sorted list of existing dotted modules it owns."""
    out: dict[str, list[str]] = {}
    for block, globs in BLOCKS.items():
        modules = sorted({m for g in globs if (m := glob_to_module(g))})
        out[block] = modules
    return out


def forbiddable(modules: list[str]) -> list[str]:
    """Modules eligible to appear in a ``forbidden_modules`` set.

    Excludes the shared ``app.models`` data layer, which every block may import.
    """
    return [m for m in modules if not _is_model(m)]


def load_depends_on() -> dict[str, list[str]]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {b["id"]: list(b.get("depends_on", [])) for b in registry}


def _fmt_modules(modules: list[str]) -> str:
    return "\n".join(f"    {m}" for m in sorted(modules))


def build_contracts() -> list[dict]:
    """Return an ordered list of contract dicts (id, name, options)."""
    block_modules = resolve_block_modules()
    depends_on = load_depends_on()
    feature_blocks = [b for b in BLOCKS if b != CORE_BLOCK]

    contracts: list[dict] = []

    # --- Core independence -----------------------------------------------------
    core_sources = block_modules.get(CORE_BLOCK, [])
    feature_forbidden = sorted(
        {m for b in feature_blocks for m in forbiddable(block_modules.get(b, []))}
    )
    if core_sources and feature_forbidden:
        contracts.append(
            {
                "id": "core-independence",
                "name": "core (app.core, app.db, app.api.deps) imports no feature block",
                "lines": [
                    "type = forbidden",
                    "source_modules =",
                    _fmt_modules(core_sources),
                    "forbidden_modules =",
                    _fmt_modules(feature_forbidden),
                    # Direct-only: a core module must never *directly* import a
                    # feature block. The worker runner legitimately imports the
                    # composition root (app.main) and the worker registry
                    # (app.workers), which in turn wire up features indirectly;
                    # that entrypoint indirection is not a sideways dependency.
                    "allow_indirect_imports = True",
                ],
            }
        )

    # --- Per-block depends_on enforcement -------------------------------------
    for block in feature_blocks:
        sources = block_modules.get(block, [])
        if not sources:
            continue
        allowed = set(depends_on.get(block, [])) | {CORE_BLOCK, block}
        forbidden_blocks = [b for b in feature_blocks if b not in allowed]
        forbidden_modules = sorted(
            {m for b in forbidden_blocks for m in forbiddable(block_modules.get(b, []))}
        )
        if not forbidden_modules:
            continue
        deps = ", ".join(sorted(depends_on.get(block, []))) or "(none)"
        contracts.append(
            {
                "id": f"block-{block}",
                "name": f"{block} may only import core + declared depends_on ({deps})",
                "lines": [
                    "type = forbidden",
                    "source_modules =",
                    _fmt_modules(sources),
                    "forbidden_modules =",
                    _fmt_modules(forbidden_modules),
                    # Only DIRECT sideways imports are violations; importing core
                    # indirectly through the app.core_api facade is allowed.
                    "allow_indirect_imports = True",
                ],
            }
        )

    return contracts


def render_config(contracts: list[dict]) -> str:
    header = (
        "# AUTO-GENERATED by scripts/blocks/gen_importlinter.py — DO NOT EDIT BY HAND.\n"
        "#\n"
        "# Regenerate with:  python3 scripts/blocks/gen_importlinter.py\n"
        "#\n"
        "# Contracts are derived from docs/blocks/registry.json (each block's\n"
        "# depends_on) + the BLOCKS path map in scripts/blocks/inventory.py. Every\n"
        "# block may always import app.core_api, app.core, app.db and app.models.\n"
        "# The enforced subset (clean contracts) lives in .importlinter-enforced and\n"
        "# is what `make ci.backend` runs; the rest are tracked in\n"
        "# docs/blocks/boundary-violations.md.\n"
        "\n"
        "[importlinter]\n"
        "root_package = app\n"
    )
    blocks = [header]
    for c in contracts:
        section = [f"\n[importlinter:contract:{c['id']}]", f"name = {c['name']}"]
        section.extend(c["lines"])
        blocks.append("\n".join(section) + "\n")
    return "".join(blocks)


def run_lint_imports() -> tuple[str, int]:
    proc = subprocess.run(
        ["uv", "run", "lint-imports"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr, proc.returncode


_NOT_ALLOWED = re.compile(r"([\w.]+) is not allowed to import ([\w.]+)")


def _normalize(text: str) -> str:
    """Collapse all whitespace so Import Linter's terminal line-wrapping (which
    splits long contract names / violation lines across lines) does not defeat
    matching."""
    return re.sub(r"\s+", " ", text)


def contract_violations(cid: str) -> list[str]:
    """Run a single contract and return its ``A is not allowed to import B`` lines."""
    proc = subprocess.run(
        ["uv", "run", "lint-imports", "--contract", cid],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    norm = _normalize(proc.stdout + proc.stderr)
    seen: dict[str, None] = {}
    for src, dst in _NOT_ALLOWED.findall(norm):
        seen[f"{src} -> {dst}"] = None
    return sorted(seen)


def parse_results(output: str, contracts: list[dict]) -> dict[str, dict]:
    """Map contract-id -> {name, kept, details} from lint-imports output.

    Pass/fail is read from the normalized summary (``<name> KEPT|BROKEN``); the
    offending imports for broken contracts are gathered with a focused
    per-contract run, which is both easier to parse and only needed for the few
    contracts that fail.
    """
    norm = _normalize(output)
    results: dict[str, dict] = {}
    for c in contracts:
        name = _normalize(c["name"]).strip()
        if f"{name} BROKEN" in norm:
            kept = False
        elif f"{name} KEPT" in norm:
            kept = True
        else:
            # Unknown — treat as not-enforced so CI never silently relies on it.
            kept = False
        details = [] if kept else contract_violations(c["id"])
        results[c["id"]] = {"name": c["name"], "kept": kept, "details": details}
    return results


def write_enforced(results: dict[str, dict], contracts: list[dict]) -> list[str]:
    enforced = [c["id"] for c in contracts if results[c["id"]]["kept"]]
    body = (
        "# AUTO-GENERATED by scripts/blocks/gen_importlinter.py — DO NOT EDIT BY HAND.\n"
        "# Enforced (currently-passing) Import Linter contract ids, one per line.\n"
        "# `make blocks.lint.backend` runs `lint-imports` limited to these via\n"
        "# --contract, so the enforced subset gates CI while the not-yet-clean\n"
        "# contracts (see docs/blocks/boundary-violations.md) stay tracked but\n"
        "# non-blocking until decoupled.\n"
    )
    body += "".join(f"{cid}\n" for cid in enforced)
    ENFORCED_PATH.write_text(body, encoding="utf-8")
    return enforced


def write_violations(results: dict[str, dict], contracts: list[dict]) -> list[str]:
    broken = [c for c in contracts if not results[c["id"]]["kept"]]
    lines = [
        "# Block boundary violations (decoupling worklist)",
        "",
        "<!-- AUTO-GENERATED by scripts/blocks/gen_importlinter.py — do not edit by hand. -->",
        "",
        "Each section below is an Import Linter contract that **does not pass yet**: the",
        "block has direct sideways imports into sibling blocks it does not declare in its",
        "`depends_on`. These contracts are defined in `backend/.importlinter` but are",
        "*excluded* from the enforced subset (`backend/.importlinter-enforced`) until the",
        "listed imports are severed (typically by routing through `app.core_api` or",
        "promoting a shared dependency). The core-independence contract and all",
        "already-clean blocks ARE enforced in `make ci.backend`.",
        "",
        "Regenerate this file with `python3 scripts/blocks/gen_importlinter.py`.",
        "",
    ]
    if not broken:
        lines.extend(
            [
                "**No violations — every block boundary contract currently passes,**",
                "so every contract in `backend/.importlinter` is in the enforced subset.",
                "",
                "This means no block has a *direct* sideways import into a sibling block",
                "it does not declare in `depends_on`; the manifests are honest. Import",
                "Linter now guards against that drift being introduced. The broader",
                "extraction worklist (including *indirect* coupling that must be severed",
                "to physically extract a block) lives in",
                "`docs/blocks/coupling-report.json` (regenerated by",
                "`scripts/blocks/inventory.py`).",
                "",
                "If a future change adds an undeclared sideways import, rerunning the",
                "generator will move the offending block's contract out of the enforced",
                "subset and list its bad imports here, grouped by block.",
            ]
        )
    else:
        lines.append(f"**{len(broken)} contract(s) still failing.**")
        lines.append("")
        for c in broken:
            res = results[c["id"]]
            lines.append(f"## `{c['id']}` — {res['name']}")
            lines.append("")
            details = res["details"]
            if details:
                lines.append("Offending import chains:")
                lines.append("")
                for d in details:
                    lines.append(f"- `{d}`")
            else:
                lines.append("_(Run `cd backend && uv run lint-imports "
                             f"--contract {c['id']}` for the offending imports.)_")
            lines.append("")
    VIOLATIONS_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return [c["id"] for c in broken]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Only (re)write backend/.importlinter; skip running lint-imports.",
    )
    args = parser.parse_args()

    contracts = build_contracts()
    CONFIG_PATH.write_text(render_config(contracts), encoding="utf-8")
    print(f"wrote {CONFIG_PATH.relative_to(REPO_ROOT)} ({len(contracts)} contracts)")

    if args.config_only:
        return 0

    output, _ = run_lint_imports()
    results = parse_results(output, contracts)
    enforced = write_enforced(results, contracts)
    broken = write_violations(results, contracts)

    print(f"wrote {ENFORCED_PATH.relative_to(REPO_ROOT)} ({len(enforced)} enforced)")
    print(f"wrote {VIOLATIONS_PATH.relative_to(REPO_ROOT)} ({len(broken)} broken)")
    print(f"  enforced: {', '.join(enforced) or '(none)'}")
    print(f"  broken:   {', '.join(broken) or '(none)'}")

    if "core-independence" in broken:
        print(
            "ERROR: core-independence contract is BROKEN — core must stay "
            "independent of feature blocks.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
