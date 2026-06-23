#!/usr/bin/env python3
"""Build the machine-readable block registry from the BLOCK.md manifests.

Run from the repo root::

    python3 scripts/blocks/build_registry.py            # write registry.json + README.md
    python3 scripts/blocks/build_registry.py --print     # print registry.json to stdout
    python3 scripts/blocks/build_registry.py --strict     # also fail on dependency cycles

Scans ``docs/blocks/*/BLOCK.md``, parses each YAML frontmatter (PyYAML if it is
importable, otherwise a minimal stdlib frontmatter parser), and writes:

* ``docs/blocks/registry.json`` — a sorted JSON array of every block with its
  ``id``, ``name``, ``tier``, ``status``, ``summary``, ``depends_on``,
  ``external_integrations``, ``owns_paths`` and ``extraction_effort``.
* ``docs/blocks/README.md`` — the human-facing North Star catalog, rendered from
  the same data.

It also builds the dependency graph and **fails with a non-zero exit code** when:

* any ``depends_on`` entry references a block id that has no manifest, or
* any non-core block owns a ``db_table`` but omits ``core`` from ``depends_on``.

Dependency **cycles** are real and intentional in this codebase — the manifests
document genuine runtime import cycles (``voice ↔ messaging``,
``agent-brain ↔ voice`` …) in their ``extraction_notes``. Hard-failing on them
would make the guard impossible to satisfy without falsifying the manifests, so
cycles are reported loudly (and recorded for the catalog) but do not fail the
build unless ``--strict`` is passed.

stdlib only (PyYAML used opportunistically if present).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # PyYAML is nice-to-have; the minimal parser below is the guaranteed path.
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised when PyYAML is absent
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCKS_DIR = REPO_ROOT / "docs" / "blocks"
REGISTRY_PATH = BLOCKS_DIR / "registry.json"
README_PATH = BLOCKS_DIR / "README.md"

# Fields copied verbatim into each registry entry, in this exact order.
REGISTRY_FIELDS = (
    "id",
    "name",
    "tier",
    "status",
    "summary",
    "depends_on",
    "external_integrations",
    "owns_paths",
    "extraction_effort",
)

TIER_ORDER = ["core", "A", "B", "C"]
TIER_LABELS = {
    "core": "Core — shared substrate",
    "A": "Tier A — headline / standalone-sellable",
    "B": "Tier B — supporting capabilities",
    "C": "Tier C — peripheral / cross-cutting",
}


class ManifestError(RuntimeError):
    """Raised when a manifest is malformed or the graph is invalid."""


# --------------------------------------------------------------------------- #
# Frontmatter parsing
# --------------------------------------------------------------------------- #
def _strip_inline_comment(value: str) -> str:
    """Drop a trailing `` # comment`` and surrounding quotes from a scalar."""
    if value.startswith("#"):
        return ""
    idx = value.find(" #")
    if idx != -1:
        value = value[:idx]
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value.strip()


def _split_flow_list(inner: str) -> list[str]:
    return [_strip_inline_comment(part) for part in inner.split(",") if part.strip()]


def _extract_frontmatter_block(text: str, source: Path) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ManifestError(f"{source}: missing opening '---' frontmatter fence")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    raise ManifestError(f"{source}: missing closing '---' frontmatter fence")


def _parse_frontmatter_minimal(block: str) -> dict:
    """Parse the flat key -> (scalar | list) frontmatter without PyYAML."""
    data: dict[str, object] = {}
    lines = block.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in raw:
            raise ManifestError(f"unparseable frontmatter line: {raw!r}")
        key, _, rest = raw.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest.startswith("["):
            inner = rest[1 : rest.rfind("]")] if "]" in rest else rest[1:]
            data[key] = _split_flow_list(inner)
            i += 1
            continue
        if rest == "":
            # Either a block list of `- item` lines, or an empty scalar.
            items: list[str] = []
            j = i + 1
            while j < n:
                nxt = lines[j]
                stripped = nxt.strip()
                if stripped.startswith("- "):
                    items.append(_strip_inline_comment(stripped[2:].strip()))
                    j += 1
                elif stripped == "":
                    j += 1
                else:
                    break
            if items:
                data[key] = items
                i = j
            else:
                data[key] = ""
                i += 1
            continue
        data[key] = _strip_inline_comment(rest)
        i += 1
    return data


def parse_manifest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    block = _extract_frontmatter_block(text, path)
    if yaml is not None:
        parsed = yaml.safe_load(block)
        if not isinstance(parsed, dict):
            raise ManifestError(f"{path}: frontmatter did not parse to a mapping")
        data = parsed
    else:
        data = _parse_frontmatter_minimal(block)

    def as_list(value: object) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]

    block_id = str(data.get("id", "")).strip()
    if not block_id:
        raise ManifestError(f"{path}: manifest is missing required 'id'")

    try:
        source = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        source = path.as_posix()

    return {
        "id": block_id,
        "name": str(data.get("name", "")).strip(),
        "tier": str(data.get("tier", "")).strip(),
        "status": str(data.get("status", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "depends_on": as_list(data.get("depends_on")),
        "external_integrations": as_list(data.get("external_integrations")),
        "owns_paths": as_list(data.get("owns_paths")),
        "extraction_effort": str(data.get("extraction_effort", "")).strip(),
        "db_tables": as_list(data.get("db_tables")),
        "_source": source,
    }


def load_manifests(blocks_dir: Path = BLOCKS_DIR) -> list[dict]:
    manifests = [parse_manifest(p) for p in sorted(blocks_dir.glob("*/BLOCK.md"))]
    if not manifests:
        raise ManifestError(f"no BLOCK.md manifests found under {blocks_dir}/*/")
    seen: dict[str, str] = {}
    for m in manifests:
        if m["id"] in seen:
            raise ManifestError(
                f"duplicate block id {m['id']!r} in {m['_source']} and {seen[m['id']]}"
            )
        seen[m["id"]] = m["_source"]
    return manifests


# --------------------------------------------------------------------------- #
# Graph validation
# --------------------------------------------------------------------------- #
def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Return a deterministic list of simple cycles (each as a node path)."""
    cycles: list[list[str]] = []
    seen_signatures: set[frozenset[str]] = set()
    WHITE, GREY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}

    def dfs(node: str, stack: list[str]) -> None:
        color[node] = GREY
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GREY:
                cycle = stack[stack.index(nxt) :] + [nxt]
                signature = frozenset(cycle[:-1])
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    cycles.append(cycle)
            elif color[nxt] == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for node in sorted(graph):
        if color[node] == WHITE:
            dfs(node, [])
    return cycles


def validate(manifests: list[dict]) -> list[list[str]]:
    """Hard-fail on broken invariants; return the (allowed) dependency cycles."""
    ids = {m["id"] for m in manifests}
    graph = {m["id"]: list(m["depends_on"]) for m in manifests}
    errors: list[str] = []

    for m in manifests:
        for dep in m["depends_on"]:
            if dep not in ids:
                errors.append(
                    f"{m['_source']}: depends_on references unknown block {dep!r} "
                    f"(no docs/blocks/{dep}/BLOCK.md)"
                )
        if m["id"] != "core" and m["db_tables"] and "core" not in m["depends_on"]:
            errors.append(
                f"{m['_source']}: block {m['id']!r} owns db_tables but omits 'core' "
                f"from depends_on"
            )

    if errors:
        raise ManifestError(
            "registry validation failed:\n  - " + "\n  - ".join(errors)
        )

    return find_cycles(graph)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def build_entries(manifests: list[dict]) -> list[dict]:
    entries = [{field: m[field] for field in REGISTRY_FIELDS} for m in manifests]
    entries.sort(key=lambda e: e["id"])
    return entries


def registry_json(manifests: list[dict]) -> str:
    return json.dumps(build_entries(manifests), indent=2, ensure_ascii=False) + "\n"


def _dependents_map(entries: list[dict]) -> dict[str, list[str]]:
    dependents: dict[str, list[str]] = {e["id"]: [] for e in entries}
    for e in entries:
        for dep in e["depends_on"]:
            dependents.setdefault(dep, []).append(e["id"])
    return {k: sorted(v) for k, v in dependents.items()}


def render_readme(manifests: list[dict], cycles: list[list[str]]) -> str:
    entries = build_entries(manifests)
    by_id = {e["id"]: e for e in entries}
    dependents = _dependents_map(entries)

    lines: list[str] = []
    lines.append("# Block Catalog — The Tribunal North Star")
    lines.append("")
    lines.append(
        "Every product capability in The Tribunal is described by a **block "
        "manifest** (`BLOCK.md`) so an AI agent can extract it into a new "
        "project. This catalog is the human-facing index of those manifests."
    )
    lines.append("")
    lines.append(
        "> **Generated file.** Rendered from `registry.json` by "
        "`scripts/blocks/build_registry.py`. Run `make blocks.check` to "
        "regenerate and validate; do not hand-edit."
    )
    lines.append("")
    lines.append(
        "See the [Agent Extraction Guide](./AGENT_EXTRACTION_GUIDE.md) for how an "
        "agent consumes these manifests, and the "
        "[BLOCK.md schema](./BLOCK_SCHEMA.md) for the frontmatter contract."
    )
    lines.append("")

    tiers_present = [t for t in TIER_ORDER if any(e["tier"] == t for e in entries)]
    for tier in tiers_present:
        tier_entries = [e for e in entries if e["tier"] == tier]
        lines.append(f"## {TIER_LABELS.get(tier, tier)}")
        lines.append("")
        lines.append("| Block | Summary | Depends on | Used by |")
        lines.append("| --- | --- | --- | --- |")
        for e in tier_entries:
            link = f"[`{e['id']}`](./{e['id']}/BLOCK.md)"
            name = e["name"] or e["id"]
            summary = e["summary"].replace("|", "\\|").replace("\n", " ")
            deps = [d for d in e["depends_on"] if d != e["id"]]
            deps_str = ", ".join(f"`{d}`" for d in deps) if deps else "—"
            used_by = dependents.get(e["id"], [])
            used_str = ", ".join(f"`{d}`" for d in used_by) if used_by else "—"
            lines.append(
                f"| {link}<br>{name} | {summary} | {deps_str} | {used_str} |"
            )
        lines.append("")

    lines.append("## Dependency notes")
    lines.append("")
    lines.append(
        "`core` is the mandatory substrate — every block that owns a database "
        "table, uses workspace scoping, auth, encryption, or pagination declares "
        "`depends_on: [core, …]`."
    )
    lines.append("")
    if cycles:
        lines.append(
            "The dependency graph contains **intentional cycles** that mirror "
            "real runtime import cycles (documented in each manifest's "
            "`extraction_notes`). They are reported, not treated as errors:"
        )
        lines.append("")
        for cycle in cycles:
            pretty = " → ".join(f"`{n}`" for n in cycle)
            lines.append(f"- {pretty}")
        lines.append("")
    else:
        lines.append("The dependency graph is currently acyclic.")
        lines.append("")

    lines.append("## All manifests")
    lines.append("")
    for e in entries:
        integ = e["external_integrations"]
        integ_str = (
            "; integrates " + ", ".join(f"`{i}`" for i in integ) if integ else ""
        )
        lines.append(
            f"- [`{e['id']}`](./{e['id']}/BLOCK.md) — tier `{e['tier']}`, "
            f"status `{e['status']}`, extraction effort `{e['extraction_effort']}`"
            f"{integ_str}."
        )
    lines.append("")
    lines.append(
        "_Generated by `scripts/blocks/build_registry.py`. Source of truth: the "
        "`BLOCK.md` manifests; machine-readable index: `registry.json`._"
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="print registry.json to stdout instead of writing files",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat dependency cycles as a fatal error (non-zero exit)",
    )
    args = parser.parse_args(argv)

    try:
        manifests = load_manifests()
        cycles = validate(manifests)
    except ManifestError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    if args.print_only:
        sys.stdout.write(registry_json(manifests))
        return 0

    REGISTRY_PATH.write_text(registry_json(manifests), encoding="utf-8")
    README_PATH.write_text(render_readme(manifests, cycles), encoding="utf-8")

    print(
        f"✓ wrote {REGISTRY_PATH.relative_to(REPO_ROOT)} and "
        f"{README_PATH.relative_to(REPO_ROOT)} "
        f"({len(manifests)} blocks)"
    )
    if cycles:
        print(f"⚠ {len(cycles)} dependency cycle(s) (intentional, documented):")
        for cycle in cycles:
            print("    " + " -> ".join(cycle))
        if args.strict:
            print("✗ --strict: failing on dependency cycles", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
