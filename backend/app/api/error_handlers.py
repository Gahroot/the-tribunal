"""Helpers for raising structured HTTP errors.

Each helper raises an ``HTTPException`` whose ``detail`` is a dict matching the
``ErrorResponse`` schema (``code``, ``message``, ``details``). The global
exception handler in ``app.main`` serializes this shape directly.
"""

from typing import Any, NoReturn

from fastapi import HTTPException, status


def _structured_detail(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def raise_not_found(entity: str, id: Any | None = None) -> NoReturn:
    """Raise a 404 for a missing entity."""
    message = f"{entity} not found" if id is None else f"{entity} {id} not found"
    details: dict[str, Any] = {"entity": entity}
    if id is not None:
        details["id"] = str(id)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_structured_detail("not_found", message, details),
    )


def raise_forbidden(reason: str) -> NoReturn:
    """Raise a 403 with a reason."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_structured_detail("forbidden", reason),
    )


def raise_bad_request(message: str, field: str | None = None) -> NoReturn:
    """Raise a 400, optionally attributing the error to a specific field."""
    details = {"field": field} if field is not None else None
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=_structured_detail("bad_request", message, details),
    )


def raise_conflict(reason: str) -> NoReturn:
    """Raise a 409 conflict."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_structured_detail("conflict", reason),
    )
