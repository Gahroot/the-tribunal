"""Scraping schemas for lead generation."""

from pydantic import BaseModel, Field


class BusinessSearchRequest(BaseModel):
    """Request schema for searching businesses."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Search query (e.g., 'plumbers in Austin TX')",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=60,
        description="Maximum number of results to return",
    )


class BusinessResult(BaseModel):
    """Schema for a single business result."""

    place_id: str = Field(..., description="Google Places ID")
    name: str = Field(..., description="Business name")
    address: str = Field(default="", description="Formatted address")
    phone_number: str | None = Field(default=None, description="Phone number")
    website: str | None = Field(default=None, description="Website URL")
    rating: float | None = Field(default=None, description="Google rating (1-5)")
    review_count: int = Field(default=0, description="Number of reviews")
    types: list[str] = Field(default_factory=list, description="Business types/categories")
    business_status: str = Field(default="OPERATIONAL", description="Business status")
    has_phone: bool = Field(default=False, description="Whether business has a phone number")
    has_website: bool = Field(default=False, description="Whether business has a website")


class BusinessSearchResponse(BaseModel):
    """Response schema for business search."""

    results: list[BusinessResult] = Field(
        default_factory=list,
        description="List of business results",
    )
    total_found: int = Field(default=0, description="Total number of results found")
    query: str = Field(..., description="The search query used")


class ImportLeadsRequest(BaseModel):
    """Request schema for importing leads as contacts."""

    leads: list[BusinessResult] = Field(..., min_length=1, description="Leads to import")
    default_status: str = Field(default="new", description="Default contact status")
    add_tags: list[str] | None = Field(default=None, description="Tags to add to imported contacts")


class ImportLeadsResponse(BaseModel):
    """Response schema for lead import."""

    total: int = Field(..., description="Total leads submitted")
    imported: int = Field(default=0, description="Successfully imported count")
    skipped_duplicates: int = Field(default=0, description="Skipped due to duplicate phone")
    skipped_no_phone: int = Field(default=0, description="Skipped due to missing phone")
    errors: list[str] = Field(default_factory=list, description="Error messages")
