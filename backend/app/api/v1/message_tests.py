"""Message test management endpoints."""

import uuid
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.agent import Agent
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.contact import Contact
from app.models.message_test import (
    MessageTest,
    MessageTestStatus,
    TestContact,
    TestContactStatus,
    TestVariant,
)
from app.models.workspace import Workspace
from app.schemas.message_test import (
    ConvertToCampaignRequest,
    MessageTestAnalytics,
    MessageTestCreate,
    MessageTestResponse,
    MessageTestUpdate,
    MessageTestWithVariantsResponse,
    PaginatedMessageTests,
    SelectWinnerRequest,
    TestContactAdd,
    TestContactResponse,
    TestVariantCreate,
    TestVariantResponse,
    TestVariantUpdate,
    VariantAnalytics,
)

router = APIRouter()


def _parse_time_string(time_str: str | None) -> time | None:
    """Parse a time string like '09:00' into a datetime.time object."""
    if time_str is None:
        return None
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


# === Message Test CRUD ===


@router.get("", response_model=PaginatedMessageTests)
async def list_message_tests(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = None,
) -> PaginatedMessageTests:
    """List message tests in a workspace."""
    query = select(MessageTest).where(MessageTest.workspace_id == workspace_id)

    if status_filter:
        query = query.where(MessageTest.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(MessageTest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    tests = result.scalars().all()

    return PaginatedMessageTests(
        items=[MessageTestResponse.model_validate(t) for t in tests],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "", response_model=MessageTestWithVariantsResponse, status_code=status.HTTP_201_CREATED
)
async def create_message_test(
    workspace_id: uuid.UUID,
    test_in: MessageTestCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTest:
    """Create a new message test."""
    # Verify agent if provided
    if test_in.agent_id:
        agent_result = await db.execute(
            select(Agent).where(
                Agent.id == test_in.agent_id,
                Agent.workspace_id == workspace_id,
            )
        )
        if not agent_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

    # Convert time strings to datetime.time objects
    test_data = test_in.model_dump(exclude={"variants"})
    if "sending_hours_start" in test_data:
        test_data["sending_hours_start"] = _parse_time_string(test_data["sending_hours_start"])
    if "sending_hours_end" in test_data:
        test_data["sending_hours_end"] = _parse_time_string(test_data["sending_hours_end"])

    message_test = MessageTest(
        workspace_id=workspace_id,
        **test_data,
    )
    db.add(message_test)
    await db.flush()  # Get the ID

    # Create variants if provided
    if test_in.variants:
        for variant_data in test_in.variants:
            variant = TestVariant(
                message_test_id=message_test.id,
                **variant_data.model_dump(),
            )
            db.add(variant)
            message_test.total_variants += 1

    await db.commit()
    await db.refresh(message_test)

    # Load variants relationship
    result = await db.execute(
        select(MessageTest)
        .options(selectinload(MessageTest.variants))
        .where(MessageTest.id == message_test.id)
    )
    return result.scalar_one()


@router.get("/{test_id}", response_model=MessageTestWithVariantsResponse)
async def get_message_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTest:
    """Get a message test by ID with variants."""
    result = await db.execute(
        select(MessageTest)
        .options(selectinload(MessageTest.variants))
        .where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    return message_test


@router.put("/{test_id}", response_model=MessageTestResponse)
async def update_message_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    test_in: MessageTestUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTest:
    """Update a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    # Only allow updates on draft/paused tests
    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update draft or paused tests",
        )

    # Update fields
    update_data = test_in.model_dump(exclude_unset=True)

    # Convert time strings to datetime.time objects
    if "sending_hours_start" in update_data:
        update_data["sending_hours_start"] = _parse_time_string(update_data["sending_hours_start"])
    if "sending_hours_end" in update_data:
        update_data["sending_hours_end"] = _parse_time_string(update_data["sending_hours_end"])

    for field, value in update_data.items():
        setattr(message_test, field, value)

    await db.commit()
    await db.refresh(message_test)

    return message_test


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete running test. Pause it first.",
        )

    await db.delete(message_test)
    await db.commit()


# === Variant Management ===


@router.get("/{test_id}/variants", response_model=list[TestVariantResponse])
async def list_variants(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> list[TestVariantResponse]:
    """List variants for a message test."""
    # Verify test exists
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    variants_result = await db.execute(
        select(TestVariant)
        .where(TestVariant.message_test_id == test_id)
        .order_by(TestVariant.sort_order)
    )
    variants = variants_result.scalars().all()

    return [TestVariantResponse.model_validate(v) for v in variants]


@router.post(
    "/{test_id}/variants",
    response_model=TestVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_variant(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    variant_in: TestVariantCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> TestVariant:
    """Create a new variant for a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only add variants to draft or paused tests",
        )

    variant = TestVariant(
        message_test_id=test_id,
        **variant_in.model_dump(),
    )
    db.add(variant)
    message_test.total_variants += 1

    await db.commit()
    await db.refresh(variant)

    return variant


@router.put("/{test_id}/variants/{variant_id}", response_model=TestVariantResponse)
async def update_variant(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    variant_id: uuid.UUID,
    variant_in: TestVariantUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> TestVariant:
    """Update a variant."""
    # Verify test exists and belongs to workspace
    test_result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = test_result.scalar_one_or_none()
    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update variants on draft or paused tests",
        )

    result = await db.execute(
        select(TestVariant).where(
            TestVariant.id == variant_id,
            TestVariant.message_test_id == test_id,
        )
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found",
        )

    update_data = variant_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(variant, field, value)

    await db.commit()
    await db.refresh(variant)

    return variant


@router.delete("/{test_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    variant_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a variant."""
    # Verify test exists
    test_result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = test_result.scalar_one_or_none()
    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete variants from draft or paused tests",
        )

    result = await db.execute(
        select(TestVariant).where(
            TestVariant.id == variant_id,
            TestVariant.message_test_id == test_id,
        )
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found",
        )

    await db.delete(variant)
    message_test.total_variants -= 1
    await db.commit()


# === Contact Management ===


@router.post("/{test_id}/contacts", response_model=dict[str, int])
async def add_contacts(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    contacts_in: TestContactAdd,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Add contacts to a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only add contacts to draft or paused tests",
        )

    # Verify contacts belong to workspace
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.id.in_(contacts_in.contact_ids),
            Contact.workspace_id == workspace_id,
        )
    )
    valid_contacts = contacts_result.scalars().all()
    valid_contact_ids = {c.id for c in valid_contacts}

    # Get existing test contacts
    existing_result = await db.execute(
        select(TestContact.contact_id).where(
            TestContact.message_test_id == test_id
        )
    )
    existing_ids = {row[0] for row in existing_result.all()}

    # Add new contacts
    added_count = 0
    for contact_id in valid_contact_ids:
        if contact_id not in existing_ids:
            test_contact = TestContact(
                message_test_id=test_id,
                contact_id=contact_id,
            )
            db.add(test_contact)
            added_count += 1

    # Update test stats
    message_test.total_contacts += added_count
    await db.commit()

    return {"added": added_count}


@router.get("/{test_id}/contacts", response_model=list[TestContactResponse])
async def list_test_contacts(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    status_filter: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[TestContactResponse]:
    """List contacts in a message test."""
    # Verify test exists
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    query = select(TestContact).where(TestContact.message_test_id == test_id)

    if status_filter:
        query = query.where(TestContact.status == status_filter)

    query = query.order_by(TestContact.created_at.desc()).limit(limit)

    contacts_result = await db.execute(query)
    contacts = contacts_result.scalars().all()

    return [TestContactResponse.model_validate(c) for c in contacts]


# === Test Actions ===


@router.post("/{test_id}/start")
async def start_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Start a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start test with status: {message_test.status}",
        )

    # Check if test has contacts
    contact_count_result = await db.execute(
        select(func.count(TestContact.id)).where(
            TestContact.message_test_id == test_id
        )
    )
    contact_count = contact_count_result.scalar() or 0

    if contact_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test has no contacts",
        )

    # Check if test has at least 2 variants
    variant_count_result = await db.execute(
        select(func.count(TestVariant.id)).where(
            TestVariant.message_test_id == test_id
        )
    )
    variant_count = variant_count_result.scalar() or 0

    if variant_count < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test needs at least 2 variants",
        )

    message_test.status = MessageTestStatus.RUNNING.value
    message_test.started_at = message_test.started_at or datetime.now(UTC)
    await db.commit()

    return {
        "status": "running",
        "message": f"Test started with {contact_count} contacts and {variant_count} variants",
    }


@router.post("/{test_id}/pause")
async def pause_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Pause a message test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause running tests",
        )

    message_test.status = MessageTestStatus.PAUSED.value
    await db.commit()

    return {"status": "paused"}


@router.post("/{test_id}/complete")
async def complete_test(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Mark a message test as completed."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    if message_test.status not in ("running", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only complete running or paused tests",
        )

    message_test.status = MessageTestStatus.COMPLETED.value
    message_test.completed_at = datetime.now(UTC)
    await db.commit()

    return {"status": "completed"}


# === Analytics ===


@router.get("/{test_id}/analytics", response_model=MessageTestAnalytics)
async def get_analytics(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTestAnalytics:
    """Get message test analytics."""
    result = await db.execute(
        select(MessageTest)
        .options(selectinload(MessageTest.variants))
        .where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    # Calculate rates
    overall_response_rate = 0.0
    if message_test.messages_sent > 0:
        overall_response_rate = (message_test.replies_received / message_test.messages_sent) * 100

    overall_qualification_rate = 0.0
    if message_test.replies_received > 0:
        overall_qualification_rate = (
            message_test.contacts_qualified / message_test.replies_received
        ) * 100

    # Build variant analytics
    variant_analytics = []
    for variant in sorted(message_test.variants, key=lambda v: v.sort_order):
        variant_analytics.append(
            VariantAnalytics(
                variant_id=variant.id,
                variant_name=variant.name,
                is_control=variant.is_control,
                contacts_assigned=variant.contacts_assigned,
                messages_sent=variant.messages_sent,
                replies_received=variant.replies_received,
                contacts_qualified=variant.contacts_qualified,
                response_rate=variant.response_rate,
                qualification_rate=variant.qualification_rate,
            )
        )

    # Determine statistical significance (simple heuristic: need at least 30 sends per variant)
    has_enough_data = (
        all(v.messages_sent >= 30 for v in message_test.variants)
        if message_test.variants
        else False
    )

    return MessageTestAnalytics(
        test_id=message_test.id,
        test_name=message_test.name,
        status=message_test.status,
        total_contacts=message_test.total_contacts,
        total_variants=message_test.total_variants,
        messages_sent=message_test.messages_sent,
        replies_received=message_test.replies_received,
        contacts_qualified=message_test.contacts_qualified,
        overall_response_rate=overall_response_rate,
        overall_qualification_rate=overall_qualification_rate,
        variants=variant_analytics,
        winning_variant_id=message_test.winning_variant_id,
        statistical_significance=has_enough_data,
    )


# === Winner Selection & Campaign Conversion ===


@router.post("/{test_id}/select-winner", response_model=MessageTestResponse)
async def select_winner(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    request: SelectWinnerRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTest:
    """Select a winning variant for the test."""
    result = await db.execute(
        select(MessageTest).where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    # Verify variant belongs to this test
    variant_result = await db.execute(
        select(TestVariant).where(
            TestVariant.id == request.variant_id,
            TestVariant.message_test_id == test_id,
        )
    )
    if not variant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found in this test",
        )

    message_test.winning_variant_id = request.variant_id
    await db.commit()
    await db.refresh(message_test)

    return message_test


@router.post("/{test_id}/convert-to-campaign", response_model=dict[str, str])
async def convert_to_campaign(
    workspace_id: uuid.UUID,
    test_id: uuid.UUID,
    request: ConvertToCampaignRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Convert a message test to a full campaign."""
    result = await db.execute(
        select(MessageTest)
        .options(selectinload(MessageTest.variants))
        .where(
            MessageTest.id == test_id,
            MessageTest.workspace_id == workspace_id,
        )
    )
    message_test = result.scalar_one_or_none()

    if not message_test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message test not found",
        )

    # Determine which message to use
    initial_message = ""
    if request.use_winning_message and message_test.winning_variant_id:
        for variant in message_test.variants:
            if variant.id == message_test.winning_variant_id:
                initial_message = variant.message_template
                break
    elif message_test.variants:
        # Use highest performing variant by response rate
        best_variant = max(message_test.variants, key=lambda v: v.response_rate)
        initial_message = best_variant.message_template

    if not initial_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No message template available for campaign",
        )

    # Create the campaign
    campaign = Campaign(
        workspace_id=workspace_id,
        agent_id=message_test.agent_id,
        name=request.campaign_name,
        description=f"Converted from message test: {message_test.name}",
        campaign_type="sms",
        status=CampaignStatus.DRAFT.value,
        from_phone_number=message_test.from_phone_number,
        use_number_pool=message_test.use_number_pool,
        initial_message=initial_message,
        ai_enabled=message_test.ai_enabled,
        qualification_criteria=message_test.qualification_criteria,
        sending_hours_start=message_test.sending_hours_start,
        sending_hours_end=message_test.sending_hours_end,
        sending_days=message_test.sending_days,
        timezone=message_test.timezone,
        messages_per_minute=message_test.messages_per_minute,
    )
    db.add(campaign)
    await db.flush()

    # Add remaining contacts if requested
    added_contacts = 0
    if request.include_remaining_contacts:
        # Get contacts that haven't been sent yet
        remaining_contacts_result = await db.execute(
            select(TestContact).where(
                TestContact.message_test_id == test_id,
                TestContact.status == TestContactStatus.PENDING.value,
            )
        )
        remaining_contacts = remaining_contacts_result.scalars().all()

        for tc in remaining_contacts:
            campaign_contact = CampaignContact(
                campaign_id=campaign.id,
                contact_id=tc.contact_id,
            )
            db.add(campaign_contact)
            added_contacts += 1

        campaign.total_contacts = added_contacts

    # Link the campaign to the test
    message_test.converted_to_campaign_id = campaign.id

    await db.commit()

    return {
        "campaign_id": str(campaign.id),
        "message": f"Campaign created with {added_contacts} contacts",
    }
