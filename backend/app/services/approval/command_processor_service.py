"""Processes inbound SMS commands (Y/N/approve/reject) for the HITL approval gate.

Intercepts inbound SMS messages from registered human operators and routes
approval/rejection commands to the ApprovalGateService before they reach
normal conversation processing.
"""

import logging
import uuid
from typing import ClassVar

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.human_profile import HumanProfile
from app.models.pending_action import PendingAction
from app.models.phone_number import PhoneNumber
from app.models.workspace import WorkspaceMembership
from app.services.approval.approval_gate_service import approval_gate_service
from app.utils.phone import normalize_phone_safe

logger = logging.getLogger(__name__)


class CommandProcessorService:
    """Processes inbound SMS commands (Y/N/approve/reject) for pending actions."""

    APPROVE_KEYWORDS: ClassVar[set[str]] = {
        "y", "yes", "approve", "ok", "go", "do it", "\U0001f44d",
    }
    REJECT_KEYWORDS: ClassVar[set[str]] = {
        "n", "no", "reject", "deny", "stop", "cancel", "\U0001f44e",
    }

    async def try_process_command(
        self,
        db: AsyncSession,
        from_number: str,
        to_number: str,
        body: str,
    ) -> bool:
        """Attempt to process an SMS as an approval command.

        Returns True if the message was consumed as a command (caller should
        NOT continue with normal SMS processing). Returns False if the message
        is not a recognised command or doesn't come from a known operator.
        """
        # 1. Normalize body
        normalized_body = body.strip().lower()

        # 2. Check if body matches approve or reject keywords
        is_approve = normalized_body in self.APPROVE_KEYWORDS
        is_reject = normalized_body in self.REJECT_KEYWORDS

        if not is_approve and not is_reject:
            return False

        # 3. Normalize the incoming phone numbers for comparison
        normalized_to = normalize_phone_safe(to_number)
        normalized_from = normalize_phone_safe(from_number)

        if not normalized_to or not normalized_from:
            logger.debug(
                "Could not normalize phone numbers: from=%s, to=%s",
                from_number,
                to_number,
            )
            return False

        # 4. Look up PhoneNumber record for to_number to get workspace_id
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.phone_number == normalized_to,
            )
        )
        phone_record = phone_result.scalar_one_or_none()
        if phone_record is None:
            logger.debug("No PhoneNumber record for %s", normalized_to)
            return False

        workspace_id: uuid.UUID = phone_record.workspace_id

        # 5. Look up HumanProfile where phone matches from_number AND workspace matches
        profile_result = await db.execute(
            select(HumanProfile).where(
                and_(
                    HumanProfile.phone_number == normalized_from,
                    HumanProfile.workspace_id == workspace_id,
                    HumanProfile.is_active.is_(True),
                )
            )
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            return False

        # 6. Find the most recent pending action for this workspace
        action_result = await db.execute(
            select(PendingAction)
            .where(
                and_(
                    PendingAction.workspace_id == workspace_id,
                    PendingAction.status == "pending",
                    PendingAction.notification_sent.is_(True),
                )
            )
            .order_by(PendingAction.created_at.desc())
            .limit(1)
        )
        action = action_result.scalar_one_or_none()

        if action is None:
            await self._send_sms_response(
                from_number=normalized_to,
                to_number=normalized_from,
                body="No pending actions to review.",
            )
            return True

        # 7. Resolve user_id from workspace membership
        user_id = await self._resolve_user_id(db, workspace_id)

        # 8. Approve or reject via the gate service
        if is_approve:
            approved_action = await approval_gate_service.approve_action(
                db, action_id=action.id, user_id=user_id, channel="sms",
            )
            await self._send_sms_response(
                from_number=normalized_to,
                to_number=normalized_from,
                body=f"\u2713 Approved: {approved_action.description}",
            )
        else:
            rejected_action = await approval_gate_service.reject_action(
                db, action_id=action.id, user_id=user_id, channel="sms",
            )
            await self._send_sms_response(
                from_number=normalized_to,
                to_number=normalized_from,
                body=f"\u2717 Rejected: {rejected_action.description}",
            )

        logger.info(
            "Processed SMS command from %s: %s action %s",
            normalized_from,
            "approve" if is_approve else "reject",
            action.id,
        )
        return True

    async def _resolve_user_id(
        self, db: AsyncSession, workspace_id: uuid.UUID
    ) -> int:
        """Get the owner/admin user_id for the workspace.

        Falls back to the first member if no owner is found.
        """
        # Prefer the workspace owner
        result = await db.execute(
            select(WorkspaceMembership.user_id)
            .where(
                and_(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.role == "owner",
                )
            )
            .limit(1)
        )
        user_id = result.scalar_one_or_none()
        if user_id is not None:
            return int(user_id)

        # Fallback: any member
        result = await db.execute(
            select(WorkspaceMembership.user_id)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .limit(1)
        )
        user_id = result.scalar_one_or_none()
        if user_id is not None:
            return int(user_id)

        # Should not happen in practice, but return 0 as a safe fallback
        logger.warning("No workspace members found for workspace %s", workspace_id)
        return 0

    async def _send_sms_response(
        self,
        from_number: str,
        to_number: str,
        body: str,
    ) -> None:
        """Send an SMS response via Telnyx API."""
        if not settings.telnyx_api_key:
            logger.debug("No Telnyx API key configured — skipping SMS response")
            return

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.telnyx.com/v2/messages",
                    headers={
                        "Authorization": f"Bearer {settings.telnyx_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_number,
                        "to": to_number,
                        "text": body,
                        "type": "SMS",
                    },
                )
                resp.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to send SMS response from %s to %s",
                from_number,
                to_number,
            )


command_processor_service = CommandProcessorService()
