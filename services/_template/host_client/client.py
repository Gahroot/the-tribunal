"""Host-side typed client for the ``__BLOCK_ID__`` service.

This lives on the **host CRM** (``backend/``) and calls the service over HTTP
with a signed service token. It is the Level-3 analogue of the frontend's
``src/lib/api/_client.ts``: the host should **regenerate a typed client from the
service's ``/openapi.json``** so a service API change surfaces as a host-side
type error before deploy (see ``README.md`` in this folder).

This stub shows the shape — auth, base URL, one call, and a signed event the
service would POST *to* the host (handled by the host's webhook router).
"""

from __future__ import annotations

import httpx


class __BLOCK_CLASS__ServiceClient:
    """Thin httpx wrapper the host uses to call the ``__BLOCK_ID__`` service.

    Args:
        base_url: the service's public URL (e.g. ``https://voice.up.railway.app``).
        token_factory: callable returning a fresh service token for a workspace,
            e.g. ``lambda wid: create_service_token(workspace_id=wid, block_id="__BLOCK_ID__")``
            minted with the host's ``SECRET_KEY`` (see ``app/core/security.py``).
        timeout: per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        token_factory,
        *,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_factory = token_factory
        self._timeout = timeout

    def _headers(self, workspace_id: int | str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_factory(workspace_id)}"}

    def status(self, workspace_id: int | str) -> dict:
        """Example call: GET /api/v1/status scoped to a workspace."""
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self._base_url}/api/v1/status",
                headers=self._headers(workspace_id),
            )
            resp.raise_for_status()
            return resp.json()
