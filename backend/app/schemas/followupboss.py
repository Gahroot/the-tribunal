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


class FUBConnectRequest(BaseModel):
    """Request body for verifying and saving a FUB key on a workspace."""

    api_key: str = Field(..., min_length=1)


class FUBConnectionStatus(BaseModel):
    """Whether a workspace has a saved, usable Follow Up Boss connection.

    Never carries the API key (or any fragment of it).
    """

    connected: bool
    account_name: str | None = None


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


class FUBImportFailure(BaseModel):
    """Why one FUB person was not imported (no PII)."""

    fub_id: int | None = None
    reason: str


class FUBImportResponse(BaseModel):
    """Result of importing FUB contacts.

    ``skipped`` counts people already present in the workspace (a re-run of the
    same import skips everything it imported before). ``failures`` lists up to
    the first 50 failed rows with a reason.
    """

    imported: int
    skipped: int
    failed: int
    failures: list[FUBImportFailure] = []
    # Workspace IDs for successfully imported or already-present people.
    contact_ids: list[int] = []
