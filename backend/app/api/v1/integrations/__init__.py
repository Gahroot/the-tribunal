"""Integration endpoint package.

Exposes the credential-management router as ``router`` for backward
compatibility with existing imports, plus per-provider sub-routers
(e.g. Follow Up Boss) as submodules.
"""

from app.api.v1.integrations.credentials import router

__all__ = ["router"]
