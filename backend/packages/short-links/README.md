# tribunal-short-links

Extracted package for the **short-links** block.

> Mirrors `docs/blocks/short-links/BLOCK.md`. Fill this in as the block's source is
> moved into `src/tribunal_short_links/` during extraction.

## Mount

```python
from fastapi import FastAPI
from tribunal_short_links import get_router, register_workers  # register_workers optional

app = FastAPI()
app.include_router(get_router(), prefix="/api/v1")
```

Also: import `tribunal_short_links.models` so its tables register in `Base.metadata`, and add
`tribunal_short_links.migrations` to Alembic `version_locations`.

## Contract

| Export | Required | Purpose |
|---|---|---|
| `get_router() -> APIRouter` | yes | block HTTP surface, mounted via `include_router` |
| `register_workers(registry)` | optional | hook workers into host `start_all_workers` |
| `tribunal_short_links.models` | tables only | SQLAlchemy models on the shared `Base` |
| `tribunal_short_links/migrations/` | tables only | Alembic `version_locations` directory |

## Environment variables

_TODO: list each env var this block reads via `app.core_api.settings`, mirroring
the `env_vars` field in `docs/blocks/short-links/BLOCK.md`._

## Core contract

Imports core primitives **only** through `app.core_api` (settings, DB session,
auth/workspace deps, pagination, encryption vault, worker base, automation bus).
No deep `app.core.*` / `app.db.*` / `app.api.deps` imports, no `os.environ`, no
hardcoded secrets.
