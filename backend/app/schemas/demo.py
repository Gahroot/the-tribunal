"""Demo endpoint schemas for landing page."""

from pydantic import BaseModel, EmailStr, field_validator


class DemoCallRequest(BaseModel):
    """Request to trigger a demo call."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        # Remove all non-digit characters
        digits = "".join(c for c in v if c.isdigit())

        # Validate US number (10 or 11 digits)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)


class DemoTextRequest(BaseModel):
    """Request to trigger a demo text."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        # Remove all non-digit characters
        digits = "".join(c for c in v if c.isdigit())

        # Validate US number (10 or 11 digits)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)


class DemoResponse(BaseModel):
    """Response from demo request."""

    success: bool
    message: str


class LeadSubmitRequest(BaseModel):
    """Request to submit a lead from the landing page."""

    first_name: str
    last_name: str | None = None
    phone_number: str
    email: EmailStr | None = None
    company_name: str | None = None
    notes: str | None = None
    source: str | None = "landing_page"
    trigger_call: bool = False
    trigger_text: bool = False

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        """Validate first name is not empty."""
        if not v or not v.strip():
            msg = "First name is required"
            raise ValueError(msg)
        return v.strip()


class LeadSubmitResponse(BaseModel):
    """Response from lead submission."""

    success: bool
    message: str
    contact_id: int | None = None
    demo_initiated: bool = False
