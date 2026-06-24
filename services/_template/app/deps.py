"""FastAPI dependencies: service-token auth + current workspace resolution."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Header, HTTPException, status

from app.security import decode_service_token


def current_workspace_id(
    authorization: Annotated[str | None, Header()] = None,
) -> int:
    """Resolve the calling workspace from the host's service token.

    The host has already authenticated the user and resolved the workspace; the
    service trusts the ``workspace_id`` claim on the signed service token. This is
    a bearer between two trusted backends over TLS — it is **not** user auth.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing service token"
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_service_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid service token"
        ) from None
    try:
        return int(payload["workspace_id"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="missing workspace_id"
        ) from None
