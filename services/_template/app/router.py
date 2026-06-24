"""Business HTTP surface for the ``__BLOCK_ID__`` service.

Replace the placeholder routes below with the block's real endpoints. Every
authenticated route resolves its workspace through :func:`current_workspace_id`
(the signed service token), so the service never re-implements user auth.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import settings
from app.deps import current_workspace_id

router = APIRouter()

WorkspaceId = Annotated[int, Depends(current_workspace_id)]


@router.get("/status")
async def status(workspace_id: WorkspaceId) -> dict[str, str]:
    """Placeholder health-of-business route. Replace with real endpoints."""
    return {
        "block": settings.block_id,
        "workspace_id": str(workspace_id),
        "status": "ok",
    }
