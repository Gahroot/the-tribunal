"""Schemas for bulk workspace-member creation.

Lets a workspace owner/admin provision many team logins in one request — the
home-service onboarding case where a shop adds a whole roster of technicians,
dispatchers, and sales reps at once instead of sending invitations one by one.
"""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.core.roles import AssignableRole

# Upper bound on a single batch. Keeps the request transaction bounded and
# caps the blast radius of a malformed/abusive payload.
MAX_BULK_MEMBERS = 100


class BulkMemberItem(BaseModel):
    """One member to provision in a bulk request."""

    email: EmailStr
    full_name: str | None = Field(None, max_length=255)
    role: AssignableRole = "member"
    # Optional initial password. When omitted, a strong temporary password is
    # generated server-side and returned once in the result so the admin can
    # hand it off. Ignored for emails that already have an account.
    password: str | None = Field(None, min_length=8, max_length=128)


class BulkMemberCreateRequest(BaseModel):
    """Request body for bulk member creation."""

    members: list[BulkMemberItem] = Field(..., min_length=1, max_length=MAX_BULK_MEMBERS)


# Outcome of processing a single input row.
#   created         — new user account + membership created
#   added_existing  — existing account attached to this workspace as a member
#   already_member  — existing account was already a member; nothing changed
#   skipped         — row not applied (duplicate in request, permission, or conflict)
BulkMemberStatus = Literal["created", "added_existing", "already_member", "skipped"]


class BulkMemberResultItem(BaseModel):
    """Per-row outcome for a bulk member creation request."""

    email: str
    status: BulkMemberStatus
    user_id: int | None = None
    role: str | None = None
    # Present only for freshly created accounts whose password was generated
    # server-side. Returned exactly once — it is not stored in plaintext.
    temporary_password: str | None = None
    error: str | None = None


class BulkMemberCreateResponse(BaseModel):
    """Aggregate result of a bulk member creation request."""

    total: int
    created: int
    added_existing: int
    already_member: int
    skipped: int
    results: list[BulkMemberResultItem]
