"""Follow Up Boss integration schemas."""

from pydantic import BaseModel, Field


class FUBVerifyRequest(BaseModel):
    """Request body for verifying a FUB API key."""

    api_key: str = Field(..., min_length=1)


class FUBVerifyResponse(BaseModel):
    """Result of verifying a FUB API key."""

    valid: bool
    name: str | None = None
    email: str | None = None


class FUBContact(BaseModel):
    """A contact from Follow Up Boss."""

    id: int
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    stage: str | None = None
    tags: list[str] = []
    last_activity: str | None = None
    source: str | None = None


class FUBPeopleResponse(BaseModel):
    """Paginated list of FUB contacts."""

    contacts: list[FUBContact]
    total: int
    has_more: bool


class FUBImportRequest(BaseModel):
    """Request body for importing FUB contacts."""

    workspace_id: str
    contact_ids: list[int] | None = None
    import_all: bool = False


class FUBImportResponse(BaseModel):
    """Result of importing FUB contacts."""

    imported: int
    skipped: int
    failed: int
