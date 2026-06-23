# Backend Block Packaging Pattern

How an **extracted backend block** is packaged so it can be mounted into any
FastAPI app and bring its own database migrations.

This is the backend mirror of `frontend/packages/README.md`. The frontend
extracts blocks into npm-workspace packages (`@tribunal/<id>`); the backend
extracts them into **uv-workspace** Python packages (`tribunal-<id>`) under
`backend/packages/<id>/`.

> **Scope.** This document defines a *pattern* plus reference scaffolding. It does
> not extract any block. Moving real block source into a package happens in
> per-block extraction tasks, driven by each block's `docs/blocks/<id>/BLOCK.md`
> manifest. Read `BLOCK_SCHEMA.md` and `AGENT_EXTRACTION_GUIDE.md` first.

---

## The contract

An extracted backend block is a Python package that exposes a **fixed, mountable
surface**. A host FastAPI app wires the block by importing exactly these names —
nothing reaches into the block's internals.

```python
from tribunal_<id> import get_router, register_workers
```

### 1. `get_router() -> APIRouter` (required)

The block's entire HTTP surface as a single `fastapi.APIRouter`. The host mounts
it the same way `app/main.py` mounts every router today:

```python
from fastapi import FastAPI
from tribunal_<id> import get_router

app = FastAPI()
app.include_router(get_router(), prefix="/api/v1")
```

Rules:

- Return a **router**, not the app. The host owns the prefix and tags.
- All routes already carry their own auth/workspace dependencies (via
  `app.core_api` — see *Settings & core contract* below). Mounting must not be
  required to re-apply tenancy.
- If the block has both authenticated and public routers (like `offers.py` has
  `router` + `public_router`), `get_router()` returns one combined router and the
  block documents the sub-prefixes in its `README.md`. A block MAY additionally
  export `get_public_router()` when the host must mount public routes under a
  different prefix (e.g. `/api/v1/p`).

### 2. `register_workers(registry)` (optional)

Hook the block's background workers into the host's `start_all_workers()`. The
host passes its worker registry; the block appends one `WorkerSpec` per worker.

```python
from app.core_api import BaseWorker, WorkerRegistry

class ExampleWorker(BaseWorker):
    COMPONENT_NAME = "example_worker"
    async def _process_items(self) -> None: ...

_registry = WorkerRegistry(ExampleWorker)

def register_workers(registry) -> None:
    """Append this block's workers to the host worker registry.

    ``registry`` is any object with ``.add(spec)`` that accepts the host's
    ``WorkerSpec`` shape (name, registry, dependencies, optional enabled
    predicate). See ``app/workers/__init__.py::WORKER_SPECS``.
    """
    registry.add(
        name="example_worker",
        registry=_registry,
        dependencies=("postgres",),
    )
```

Rules:

- A block with **no** workers omits `register_workers` entirely (it is optional).
- Each worker subclasses `app.core_api.BaseWorker` and is managed by a
  `app.core_api.WorkerRegistry` singleton, exactly like every worker in
  `app/workers/` today.
- The block never imports the host's `WORKER_SPECS` or `start_all_workers`; it
  only *contributes* specs through `register_workers`. The host decides startup
  order and `RUN_BACKGROUND_WORKERS` gating.

> **Host adapter.** The repo's current `start_all_workers()` iterates a static
> `WORKER_SPECS` tuple. To accept block contributions, the host wraps that tuple
> in a small collector exposing `add(**spec_kwargs)` that constructs a
> `WorkerSpec` and appends it before startup. Implementing that collector is a
> host concern, not part of the block contract.

### 3. `models` importable (required for Alembic autogenerate)

The block ships a `models.py` (or `models/` package) of SQLAlchemy declarative
classes bound to the **shared** `Base` / `MetaData`. When the host imports the
block's models, their tables register into `Base.metadata`, so
`alembic revision --autogenerate` and `alembic check` see them.

```python
# tribunal_<id>/models.py
from app.core_api import ...          # core primitives only
from app.db.base import Base          # the shared declarative Base

class Example(Base):
    __tablename__ = "examples"
    ...
```

How the host makes them visible to Alembic: `backend/alembic/env.py` calls
`import_model_modules()` (from `app/db/model_registry.py`), which imports every
module under `app.models`. A mounted block extends that discovery — either by:

- adding the block's models package to the registry's scan list, or
- importing `tribunal_<id>.models` from the host's model aggregation point
  (e.g. `app/models/__init__.py`) once the block is a dependency.

Either way the rule is: **block tables must be in `Base.metadata` before
autogenerate runs.** A block whose models are not imported will be silently
dropped by `alembic check` as a phantom diff.

### 4. `migrations/` directory (Alembic `version_locations`)

The block carries its own Alembic revision files in
`tribunal_<id>/migrations/`. The host adds that directory to Alembic's
`version_locations` so block revisions live in the **same history** as the app's.

#### How this repo's Alembic is configured (verified)

`backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
```

- `script_location = alembic` → revisions default to `backend/alembic/versions/`
  (there is **no** explicit `version_locations` line today, so it falls back to
  `<script_location>/versions`).
- `version_path_separator = os` is **already set** — this is exactly what is
  needed to list *multiple* version directories, separated by the OS path
  separator (`:` on POSIX, `;` on Windows).

`backend/alembic/env.py` imports the shared metadata and pre-imports every model
module before configuring the context:

```python
from app.db.base import Base
from app.db.model_registry import import_model_modules
import_model_modules()
target_metadata = Base.metadata
```

So today the repo runs **one shared, linear Alembic chain** in
`alembic/versions/` (see `AGENT_EXTRACTION_GUIDE.md` and every block manifest's
`alembic_migrations: shared chain — …`).

#### Recommended approach: shared chain via `version_locations` + branch labels

Because there is one shared chain today, keep block revisions **in that same
history** rather than spinning up a parallel Alembic environment. To mount a
block's migrations the host adds its directory to `version_locations`.

**Option A — static, in `alembic.ini`** (simplest when blocks are known):

```ini
[alembic]
script_location = alembic
version_path_separator = os
version_locations = %(here)s/alembic/versions packages/example/src/tribunal_example/migrations
```

**Option B — dynamic, in `env.py`** (preferred; auto-discovers mounted blocks):

```python
# in backend/alembic/env.py, after `config = context.config`
import importlib.util
from pathlib import Path

def _block_version_locations() -> list[str]:
    locations: list[str] = []
    for mod in ("tribunal_example",):  # or discover from a mounted-blocks list
        spec = importlib.util.find_spec(f"{mod}.migrations")
        if spec and spec.submodule_search_locations:
            locations.append(str(Path(next(iter(spec.submodule_search_locations)))))
    return locations

existing = config.get_main_option("version_locations") or "alembic/versions"
config.set_main_option(
    "version_locations",
    os.pathsep.join([existing, *_block_version_locations()]),
)
```

Resolving the path through `importlib.util.find_spec` keeps it correct whether
the block is an in-repo workspace member or an installed wheel.

**Branch labels.** When a block's revisions form an independent line that the
host stitches in (rather than appending linearly to the current head), give the
block's first revision a branch label and let the host merge it:

```python
# first revision in tribunal_<id>/migrations/
revision = "blk_<id>_0001"
down_revision = None
branch_labels = ("block_<id>",)
depends_on = None
```

The host then creates a normal `alembic merge` revision joining `block_<id>`
into the app head. This gives each block an isolated, relocatable revision line
while still producing a single `alembic upgrade head` for the host.

**Default recommendation (today):** since there is one shared chain, the lowest-
risk path for a freshly extracted block in a *new* project is to
`alembic revision --autogenerate` against the block's imported models in that
project (per `AGENT_EXTRACTION_GUIDE.md` step 6). Use the `version_locations` +
branch-label mechanism above when you need the block's authored revisions to
travel verbatim into a host that already has its own chain.

### 5. Settings & core contract (required)

A block **declares** its environment variables and **reads** them through
`app.core_api`'s settings — never `os.environ` directly, never a private
`app.core.config` import, never a hardcoded value.

```python
from app.core_api import settings

api_key = settings.example_api_key   # declared in core Settings; read via the facade
```

Rules:

- The block's `README.md` lists every env var it reads, mirroring the block
  manifest's `env_vars` field. Names match the core `Settings` field naming
  (`EXAMPLE_API_KEY` → `settings.example_api_key`).
- The block imports core primitives **only** through `app.core_api` — the single
  documented facade (`app/core_api/README.md`): `settings`, `DB`,
  `CurrentUser`, `get_workspace`, `apply_workspace_scope`, `paginate`,
  `BaseWorker`, `WorkerRegistry`, `emit_automation_event`, the encryption vault,
  etc. It must not reach into `app.api.deps`, `app.db.*`, `app.core.*`,
  `app.workers.base`, or `app.services.idempotency` directly.
- Per-workspace third-party credentials stay Fernet-encrypted via the core vault
  (`EncryptedString`, `encrypt_json`/`decrypt_json`) — the block does not invent
  its own secret storage.

This is what lets a block mount into *any* host: it depends on the **`core_api`
contract**, not on the host's internal module layout.

---

## Where extracted backend packages live

**Decision: `backend/packages/<block-id>/`, as a uv workspace member.**

This mirrors `frontend/packages/<block-id>/` (npm workspaces). The FastAPI app
stays at `backend/` (distribution `aicrm-backend`); each extracted block becomes
an independently packageable distribution `tribunal-<block-id>` under
`backend/packages/`.

`backend/pyproject.toml` declares the workspace:

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

uv (this repo runs uv 0.11.x) resolves every `packages/*/pyproject.toml` as a
workspace member sharing the root `uv.lock`. An empty `packages/` (the state
today) is a zero-member workspace and is harmless. Add a member with the
scaffolder below; `uv sync` then links it for local development without
publishing.

### Package layout (per block)

```
backend/packages/<block-id>/
  pyproject.toml                      # distribution tribunal-<block-id> (hatchling)
  README.md                           # public surface + env_vars, mirrors BLOCK.md
  src/
    tribunal_<block_id>/              # importable package (id with - → _)
      __init__.py                     # exports get_router, register_workers
      router.py                       # APIRouter, returned by get_router()
      service.py                      # domain logic (workspace-scoped)
      schemas.py                      # Pydantic request/response models
      models.py                       # SQLAlchemy models bound to shared Base
      migrations/                     # Alembic version_locations dir for this block
        __init__.py
        README.md
```

- Folder name is the **kebab-case** block id (matches `docs/blocks/<id>/`).
- Importable package name is the id with hyphens → underscores, prefixed
  `tribunal_` (a valid Python identifier).
- Distribution name is `tribunal-<block-id>` (PyPI-style; no `@scope`).

### Naming summary

| Aspect | Backend | Frontend (sibling) |
|---|---|---|
| Location | `backend/packages/<id>/` | `frontend/packages/<id>/` |
| Workspace | `[tool.uv.workspace] members = ["packages/*"]` | `"workspaces": ["packages/*"]` |
| Dist / pkg name | `tribunal-<id>` | `@tribunal/<id>` |
| Import name | `tribunal_<id_underscored>` | `@tribunal/<id>` |
| Entry | `__init__.py` → `get_router`, `register_workers` | `src/index.ts` → `public_api` |
| Version | `0.1.0` | `0.1.0` |
| README | mirrors `docs/blocks/<id>/BLOCK.md` | mirrors `docs/blocks/<id>/BLOCK.md` |

---

## Scaffolding a new package

From the repo root:

```bash
uv run --project backend python scripts/blocks/scaffold_backend_block.py <block-id>
# or: python scripts/blocks/scaffold_backend_block.py <block-id>   (stdlib only)
```

This creates `backend/packages/<block-id>/` with `pyproject.toml`, `README.md`,
and the `src/tribunal_<block_id>/` package (`__init__.py`, `router.py`,
`service.py`, `schemas.py`, `models.py`, `migrations/`). It refuses to overwrite
an existing package and validates the id against `docs/blocks/registry.json`
when present.

After scaffolding:

1. `uv sync` from `backend/` to link the new workspace member.
2. Move the block's source into `src/tribunal_<block_id>/`, importing core only
   through `app.core_api`.
3. Build `get_router()` from the block's router(s); add `register_workers` only
   if the block owns workers.
4. Add the block's `migrations/` dir to the host `version_locations` (see §4).

---

## Mounting a block into a host (summary)

```python
# host app
from fastapi import FastAPI
from tribunal_example import get_router, register_workers  # register_workers optional

app = FastAPI()
app.include_router(get_router(), prefix="/api/v1")

# during worker startup (host's start_all_workers adapter):
register_workers(host_worker_registry)
```

Plus: import `tribunal_example.models` so its tables hit `Base.metadata`, and add
`tribunal_example.migrations` to Alembic `version_locations`. Provide the block's
declared env vars in the host environment. That is the whole integration surface.

---

## Rules of thumb

- **One block ⇄ one package ⇄ one `BLOCK.md`.** The package mirrors the manifest.
- **`get_router` is the only required runtime export.** `register_workers` is
  optional; `models` + `migrations` are required only for blocks with tables.
- **Core comes through `app.core_api`, always.** No deep core imports, no
  `os.environ`, no hardcoded secrets.
- **Migrations stay in the shared chain.** Use `version_locations` + a branch
  label to relocate authored revisions; regenerate fresh in a brand-new project.
- **Scaffolding ≠ extraction.** This pattern and scaffolder produce empty
  packages. Real source moves in per-block extraction tasks.
```