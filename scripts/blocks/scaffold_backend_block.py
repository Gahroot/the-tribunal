#!/usr/bin/env python3
"""Scaffold an extractable backend block package under backend/packages/<id>/.

Usage (from the repo root)::

    python3 scripts/blocks/scaffold_backend_block.py <block-id>

Creates ``backend/packages/<id>/`` with a ``pyproject.toml`` (distribution
``tribunal-<id>``), a ``README.md`` stub, and the importable package
``src/tribunal_<id_underscored>/`` exposing the block contract:

* ``get_router() -> APIRouter``    (required runtime surface)
* ``register_workers(registry)``   (optional worker hook)
* ``models`` / ``schemas`` / ``service`` / ``router`` modules
* a ``migrations/`` directory for Alembic ``version_locations``

It does **not** move any block source — that happens in per-block extraction
tasks. It refuses to overwrite an existing package and validates the id against
``docs/blocks/registry.json`` when present.

stdlib only — see ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Repo layout anchors (this file lives at scripts/blocks/).
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PACKAGES_DIR = REPO_ROOT / "backend" / "packages"
REGISTRY_PATH = REPO_ROOT / "docs" / "blocks" / "registry.json"

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def fail(message: str) -> None:
    print(f"\u2716 {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_id(raw_id: str) -> str:
    block_id = raw_id.strip()
    if not KEBAB_RE.match(block_id):
        fail(f'Invalid block id "{block_id}". Use a kebab-case slug, e.g. "lead-capture".')
    return block_id


def check_registry(block_id: str) -> None:
    """Warn/refuse if the id is not a known block (when a registry exists)."""
    if not REGISTRY_PATH.is_file():
        return
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"! Could not parse registry ({exc}); skipping id check.", file=sys.stderr)
        return

    if isinstance(registry, dict):
        entries = registry.get("blocks", registry.get("nodes", []))
    else:
        entries = registry
    ids = [b.get("id") for b in entries if isinstance(b, dict) and b.get("id")]
    if ids and block_id not in ids:
        fail(
            f'"{block_id}" is not a known block id in docs/blocks/registry.json.\n'
            f"  Known ids: {', '.join(sorted(ids))}"
        )


def module_name(block_id: str) -> str:
    """Importable package name: kebab id -> ``tribunal_<underscored>``."""
    return "tribunal_" + block_id.replace("-", "_")


def render_pyproject(block_id: str, module: str) -> str:
    return f"""\
[project]
name = "tribunal-{block_id}"
version = "0.1.0"
description = "Extracted '{block_id}' block from The Tribunal — mountable FastAPI block package."
readme = "README.md"
requires-python = ">=3.12"
license = "LicenseRef-Proprietary"
dependencies = [
    # The block depends on the host's core surface via the `app.core_api` facade.
    # While developed in-repo as a uv workspace member it resolves against
    # `aicrm-backend`; pin the real core dependency here when published standalone.
    "fastapi>=0.136.1",
    "sqlalchemy[asyncio]>=2.0.49",
    "pydantic>=2.13.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{module}"]

[tool.hatch.build.targets.wheel.force-include]
"src/{module}/migrations" = "{module}/migrations"
"""


def render_init(block_id: str, module: str) -> str:
    return f'''\
"""Mountable contract for the ``{block_id}`` block.

A host FastAPI app integrates this block through exactly these names:

    from {module} import get_router, register_workers

* ``get_router()`` returns the block's :class:`fastapi.APIRouter`; mount with
  ``app.include_router(get_router(), prefix="/api/v1")``.
* ``register_workers(registry)`` (optional) appends the block's background
  workers to the host worker registry.

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from .router import get_router

# Export ``register_workers`` only if this block owns background workers.
# Remove this import (and the worker spec in ``router.py``/a ``workers.py``)
# for a worker-free block.
from .router import register_workers

__all__ = ["get_router", "register_workers"]
'''


def render_router(block_id: str, module: str) -> str:
    return f'''\
"""HTTP surface for the ``{block_id}`` block.

``get_router()`` is the only required runtime export. All routes carry their own
auth/workspace dependencies via ``app.core_api`` so mounting never re-applies
tenancy.
"""

from __future__ import annotations

from fastapi import APIRouter

# Core primitives come ONLY through the documented facade. Never import
# app.api.deps / app.db.* / app.core.* / app.workers.base directly.
# Example:
#   from app.core_api import DB, WorkspaceAccess, settings


def get_router() -> APIRouter:
    """Return the block's API router for ``app.include_router(...)``."""
    router = APIRouter(tags=["{block_id}"])

    @router.get("/{block_id}/health")
    async def block_health() -> dict[str, str]:
        """Placeholder route. Replace with the block's real endpoints."""
        return {{"block": "{block_id}", "status": "ok"}}

    return router


def register_workers(registry: object) -> None:
    """Append this block's workers to the host worker registry.

    ``registry`` is any object with an ``add(...)`` method accepting the host's
    ``WorkerSpec`` shape (see ``app/workers/__init__.py``). Delete this function
    (and its export in ``__init__.py``) for a block with no workers.

    Example::

        from app.core_api import WorkerRegistry
        from .workers import {module.title().replace("_", "")}Worker

        registry.add(
            name="{module}_worker",
            registry=WorkerRegistry({module.title().replace("_", "")}Worker),
            dependencies=("postgres",),
        )
    """
    return None
'''


def render_service(block_id: str) -> str:
    return f'''\
"""Domain logic for the ``{block_id}`` block.

Keep all queries workspace-scoped through ``app.core_api`` helpers
(``apply_workspace_scope`` / ``select_workspace_owned``). Read configuration via
``app.core_api.settings`` — never ``os.environ`` or a hardcoded value.
"""

from __future__ import annotations

# from app.core_api import apply_workspace_scope, paginate, settings


class {block_id.replace("-", " ").title().replace(" ", "")}Service:
    """Entry point for the block's domain operations."""
'''


def render_schemas(block_id: str) -> str:
    return f'''\
"""Pydantic request/response schemas for the ``{block_id}`` block."""

from __future__ import annotations

from pydantic import BaseModel


class {block_id.replace("-", " ").title().replace(" ", "")}Base(BaseModel):
    """Base schema. Replace with the block's real request/response models."""
'''


def render_models(block_id: str) -> str:
    return f'''\
"""SQLAlchemy models for the ``{block_id}`` block.

Models bind to the shared declarative ``Base`` so their tables register in
``Base.metadata`` and Alembic autogenerate/``check`` can see them. The host must
import this module before running migrations (see
``docs/blocks/BACKEND_BLOCK_PATTERN.md`` \u00a73).
"""

from __future__ import annotations

# from app.db.base import Base
#
# class {block_id.replace("-", " ").title().replace(" ", "")}(Base):
#     __tablename__ = "{block_id.replace("-", "_")}s"
#     ...
'''


def render_migrations_init(block_id: str) -> str:
    return f'"""Alembic version_locations directory for the ``{block_id}`` block."""\n'


def render_migrations_readme(block_id: str, module: str) -> str:
    return f"""\
# `{module}` migrations

Alembic revision files for the **{block_id}** block live here. The host adds this
directory to Alembic `version_locations` so block revisions share the app's
history.

Resolve the path at runtime via the installed package:

```python
import importlib.util
from pathlib import Path

spec = importlib.util.find_spec("{module}.migrations")
location = str(Path(next(iter(spec.submodule_search_locations))))
# append `location` to alembic version_locations (os.pathsep-separated)
```

The repo's `backend/alembic.ini` already sets `version_path_separator = os`, so
multiple directories can be listed. Give a block's first revision a
`branch_labels = ("block_{block_id.replace("-", "_")}",)` when the host stitches
it in via `alembic merge`. See `docs/blocks/BACKEND_BLOCK_PATTERN.md` \u00a74.
"""


def render_readme(block_id: str, module: str) -> str:
    return f"""\
# tribunal-{block_id}

Extracted package for the **{block_id}** block.

> Mirrors `docs/blocks/{block_id}/BLOCK.md`. Fill this in as the block's source is
> moved into `src/{module}/` during extraction.

## Mount

```python
from fastapi import FastAPI
from {module} import get_router, register_workers  # register_workers optional

app = FastAPI()
app.include_router(get_router(), prefix="/api/v1")
```

Also: import `{module}.models` so its tables register in `Base.metadata`, and add
`{module}.migrations` to Alembic `version_locations`.

## Contract

| Export | Required | Purpose |
|---|---|---|
| `get_router() -> APIRouter` | yes | block HTTP surface, mounted via `include_router` |
| `register_workers(registry)` | optional | hook workers into host `start_all_workers` |
| `{module}.models` | tables only | SQLAlchemy models on the shared `Base` |
| `{module}/migrations/` | tables only | Alembic `version_locations` directory |

## Environment variables

_TODO: list each env var this block reads via `app.core_api.settings`, mirroring
the `env_vars` field in `docs/blocks/{block_id}/BLOCK.md`._

## Core contract

Imports core primitives **only** through `app.core_api` (settings, DB session,
auth/workspace deps, pagination, encryption vault, worker base, automation bus).
No deep `app.core.*` / `app.db.*` / `app.api.deps` imports, no `os.environ`, no
hardcoded secrets.
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        fail("Usage: python3 scripts/blocks/scaffold_backend_block.py <block-id>")

    block_id = validate_id(argv[1])
    check_registry(block_id)

    module = module_name(block_id)
    pkg_dir = PACKAGES_DIR / block_id
    if pkg_dir.exists():
        fail(f"backend/packages/{block_id}/ already exists — refusing to overwrite.")

    src_dir = pkg_dir / "src" / module
    migrations_dir = src_dir / "migrations"
    migrations_dir.mkdir(parents=True)

    files: dict[Path, str] = {
        pkg_dir / "pyproject.toml": render_pyproject(block_id, module),
        pkg_dir / "README.md": render_readme(block_id, module),
        src_dir / "__init__.py": render_init(block_id, module),
        src_dir / "router.py": render_router(block_id, module),
        src_dir / "service.py": render_service(block_id),
        src_dir / "schemas.py": render_schemas(block_id),
        src_dir / "models.py": render_models(block_id),
        migrations_dir / "__init__.py": render_migrations_init(block_id),
        migrations_dir / "README.md": render_migrations_readme(block_id, module),
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")

    rel = pkg_dir.relative_to(REPO_ROOT)
    print(f"\u2713 Created {rel}/ (tribunal-{block_id}, import {module})")
    print("  Next:")
    print("    1. Run `uv sync` from backend/ to link the workspace member.")
    print(f"    2. Move {block_id} block source into {rel}/src/{module}/.")
    print("    3. Build get_router() from the block routers; keep core imports via app.core_api.")
    print(f"    4. Add {module}.migrations to the host Alembic version_locations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
