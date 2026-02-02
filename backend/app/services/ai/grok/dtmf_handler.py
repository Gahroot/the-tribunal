"""DTMF handler for Grok voice agent.

This module provides DTMF detection and sending capabilities for IVR navigation.
It includes:
- Tracking of pending async tasks to prevent fire-and-forget bugs
- Incremental scanning to avoid re-processing full transcripts
- DTMF tag parsing from agent responses
- Callback-based DTMF sending via telephony provider
"""

import asyncio
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from app.services.ai.ivr_detector import DTMFContext, DTMFValidator, IVRStatus

logger = structlog.get_logger()


@dataclass
class DTMFHandlerConfig:
    """Configuration for DTMF handler behavior.

    Attributes:
        tag_pattern: Regex pattern to extract DTMF digits from text
        delay_between_sequences_ms: Delay between sending multiple sequences
        delay_before_first_send_ms: Delay before sending the first DTMF in a response.
            This allows IVR systems to fully stop speaking before receiving input.
        post_dtmf_cooldown_ms: Cooldown period after sending DTMF before sending another.
            This prevents rapid 0,1,2,0,2,1 patterns that confuse IVR systems.
    """

    tag_pattern: str = r"<dtmf>([0-9*#A-Dw]+)</dtmf>"
    delay_between_sequences_ms: int = 300
    delay_before_first_send_ms: int = 200
    post_dtmf_cooldown_ms: int = 3000


@dataclass
class DTMFSendResult:
    """Result from a DTMF send operation.

    Attributes:
        digits: The digits that were sent
        success: Whether the send succeeded
        error: Error message if failed
    """

    digits: str
    success: bool
    error: str | None = None


class DTMFHandler:
    """Handles DTMF detection in transcripts and sending via callbacks.

    This handler:
    1. Tracks pending async tasks to prevent fire-and-forget race conditions
    2. Uses incremental scanning to avoid re-processing the entire transcript
    3. Deduplicates DTMF sequences to prevent double-sending
    4. Splits multi-digit sequences based on IVR context

    Usage:
        handler = DTMFHandler(config, tool_callback, get_ivr_status)

        # In the audio stream loop:
        await handler.check_and_send(agent_transcript)

        # On cleanup:
        await handler.cleanup()
    """

    def __init__(
        self,
        config: DTMFHandlerConfig | None = None,
        tool_callback: Callable[[str, str, dict[str, Any]], Any] | None = None,
        get_ivr_status: Callable[[], IVRStatus | None] | None = None,
        record_dtmf_attempt: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the DTMF handler.

        Args:
            config: Handler configuration (uses defaults if None)
            tool_callback: Async callback for executing DTMF sends
            get_ivr_status: Function to get current IVR status for context
            record_dtmf_attempt: Function to record DTMF attempts in detector
        """
        self._config = config or DTMFHandlerConfig()
        self._tool_callback = tool_callback
        self._get_ivr_status = get_ivr_status
        self._record_dtmf_attempt = record_dtmf_attempt
        self._logger = logger.bind(service="dtmf_handler")

        # Compile the tag pattern
        self._pattern = re.compile(self._config.tag_pattern, re.IGNORECASE)

        # Track pending async tasks to prevent fire-and-forget issues
        self._pending_tasks: set[asyncio.Task[DTMFSendResult]] = set()

        # Track sent sequences to prevent duplicates
        self._sent_sequences: set[str] = set()

        # Track last scan position for incremental scanning
        self._last_scan_position: int = 0

        # Track if we've sent the first DTMF in current response (for pre-send delay)
        self._first_send_done: bool = False

        # Track last DTMF send time for cooldown enforcement
        self._last_dtmf_send_time: float = 0.0

        # Validator for splitting digits by context
        self._validator = DTMFValidator()

    def set_tool_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], Any],
    ) -> None:
        """Set or update the tool callback.

        Args:
            callback: Async callback function(call_id, function_name, arguments) -> result
        """
        self._tool_callback = callback

    def _is_in_cooldown(self) -> bool:
        """Check if we're in post-DTMF cooldown period.

        Returns:
            True if cooldown is active and we should skip sending.
        """
        if self._config.post_dtmf_cooldown_ms <= 0 or self._last_dtmf_send_time <= 0:
            return False

        elapsed_ms = (time.time() - self._last_dtmf_send_time) * 1000
        if elapsed_ms < self._config.post_dtmf_cooldown_ms:
            self._logger.debug(
                "dtmf_cooldown_active",
                elapsed_ms=int(elapsed_ms),
                cooldown_ms=self._config.post_dtmf_cooldown_ms,
                remaining_ms=int(self._config.post_dtmf_cooldown_ms - elapsed_ms),
            )
            return True
        return False

    async def check_and_send(self, text: str) -> list[DTMFSendResult]:  # noqa: PLR0912
        """Check transcript for DTMF tags and send them.

        This is the PRIMARY mechanism for DTMF detection since xAI function
        calling may not work reliably. Parses <dtmf>X</dtmf> tags from agent
        transcript and sends the digits via the tool callback.

        Uses incremental scanning to only check new content since last scan.
        Enforces post-DTMF cooldown to prevent rapid presses.

        Args:
            text: Full agent transcript text

        Returns:
            List of send results for any DTMF sequences found
        """
        if not text or len(text) <= self._last_scan_position:
            return []

        # Check if we're in cooldown period
        if self._is_in_cooldown():
            return []

        # Only scan new content (with some overlap for safety)
        scan_start = max(0, self._last_scan_position - 20)
        new_content = text[scan_start:]

        # Update scan position
        self._last_scan_position = len(text)

        # Find all matches in new content
        matches = self._pattern.findall(new_content)
        if not matches:
            return []

        results: list[DTMFSendResult] = []

        for digits in matches:
            # Create occurrence key based on position in full text
            # Use find on full text to get absolute position
            tag = f"<dtmf>{digits}</dtmf>"
            position = text.find(tag)
            occurrence_key = f"{position}:{digits}"

            if occurrence_key in self._sent_sequences:
                continue

            # Filter to valid DTMF characters only
            valid_chars = set("0123456789*#ABCDabcd")
            actual_digits = "".join(c for c in digits if c in valid_chars)

            if not actual_digits:
                continue

            # Get current IVR context for proper splitting
            context = DTMFContext.MENU  # Default
            if self._get_ivr_status:
                ivr_status = self._get_ivr_status()
                if ivr_status and ivr_status.menu_state:
                    context = ivr_status.menu_state.context

            # Split digits based on context
            digit_sequences = self._validator.split_dtmf_by_context(actual_digits, context)

            self._logger.info(
                "dtmf_tag_detected",
                raw_digits=digits,
                context=context.value if hasattr(context, "value") else str(context),
                will_send_as=digit_sequences,
            )

            # Mark as sent before sending to prevent duplicates
            self._sent_sequences.add(occurrence_key)

            # Send each sequence
            for i, seq in enumerate(digit_sequences):
                # Apply pre-send delay before the first DTMF in this response
                # This allows IVR systems to fully stop speaking before receiving input
                if not self._first_send_done and self._config.delay_before_first_send_ms > 0:
                    self._logger.debug(
                        "dtmf_pre_send_delay",
                        delay_ms=self._config.delay_before_first_send_ms,
                    )
                    await asyncio.sleep(self._config.delay_before_first_send_ms / 1000)
                    self._first_send_done = True

                result = await self._send_dtmf(seq)
                results.append(result)

                if result.success and self._record_dtmf_attempt:
                    self._record_dtmf_attempt(seq)

                # Add delay between sequences if multiple
                if i < len(digit_sequences) - 1:
                    await asyncio.sleep(self._config.delay_between_sequences_ms / 1000)

        return results

    async def _send_dtmf(self, digits: str) -> DTMFSendResult:
        """Send DTMF digits via the tool callback.

        Records send timestamp for cooldown enforcement.

        Args:
            digits: DTMF digits to send

        Returns:
            Result of the send operation
        """
        if not self._tool_callback:
            self._logger.warning("no_tool_callback_for_dtmf")
            return DTMFSendResult(
                digits=digits,
                success=False,
                error="Tool callback not configured",
            )

        try:
            call_id = f"dtmf_{uuid.uuid4().hex[:8]}"

            result = await self._tool_callback(
                call_id,
                "send_dtmf",
                {"digits": digits},
            )

            # Record send time for cooldown enforcement
            self._last_dtmf_send_time = time.time()

            self._logger.info(
                "dtmf_sent",
                digits=digits,
                result=result,
                cooldown_ms=self._config.post_dtmf_cooldown_ms,
            )

            return DTMFSendResult(digits=digits, success=True)

        except Exception as e:
            self._logger.exception(
                "dtmf_send_error",
                digits=digits,
                error=str(e),
            )
            return DTMFSendResult(
                digits=digits,
                success=False,
                error=str(e),
            )

    def send_async(self, digits: str) -> asyncio.Task[DTMFSendResult]:
        """Send DTMF asynchronously with task tracking.

        Unlike fire-and-forget asyncio.create_task(), this method:
        1. Creates the task
        2. Adds it to the pending set for tracking
        3. Sets up cleanup callback to remove from set when done

        Args:
            digits: DTMF digits to send

        Returns:
            Task that will complete with the send result
        """
        task = asyncio.create_task(self._send_with_tracking(digits))
        self._pending_tasks.add(task)
        task.add_done_callback(self._task_done_callback)
        return task

    async def _send_with_tracking(self, digits: str) -> DTMFSendResult:
        """Send DTMF with proper error handling for async tracking.

        Args:
            digits: DTMF digits to send

        Returns:
            Result of the send operation
        """
        try:
            return await self._send_dtmf(digits)
        except Exception as e:
            self._logger.exception("dtmf_async_send_error", digits=digits, error=str(e))
            return DTMFSendResult(
                digits=digits,
                success=False,
                error=str(e),
            )

    def _task_done_callback(self, task: asyncio.Task[DTMFSendResult]) -> None:
        """Callback when a tracked task completes.

        Args:
            task: The completed task
        """
        self._pending_tasks.discard(task)

        # Log any exceptions that occurred
        if not task.cancelled():
            exc = task.exception()
            if exc:
                self._logger.error(
                    "dtmf_task_exception",
                    error=str(exc),
                )

    async def cleanup(self) -> None:
        """Cancel all pending tasks and wait for cleanup.

        Call this when the session is ending to ensure no orphaned tasks.
        """
        if not self._pending_tasks:
            return

        self._logger.info(
            "dtmf_handler_cleanup",
            pending_count=len(self._pending_tasks),
        )

        # Cancel all pending tasks
        for task in self._pending_tasks:
            task.cancel()

        # Wait for cancellations to complete (with timeout)
        if self._pending_tasks:
            await asyncio.wait(
                self._pending_tasks,
                timeout=1.0,
                return_when=asyncio.ALL_COMPLETED,
            )

        self._pending_tasks.clear()

    def reset(self) -> None:
        """Reset handler state for a new conversation.

        Clears sent sequences, scan position, and cooldown timer.
        Does NOT cancel pending tasks - call cleanup() first if needed.
        """
        self._sent_sequences.clear()
        self._last_scan_position = 0
        self._first_send_done = False
        self._last_dtmf_send_time = 0.0
        self._logger.debug("dtmf_handler_reset")

    def reset_for_new_response(self) -> None:
        """Reset scan position for a new response.

        Called when a new response starts. Resets the incremental scan position
        so DTMF tags in the new response transcript will be detected.

        Does NOT clear sent_sequences to maintain deduplication across responses.
        """
        self._last_scan_position = 0
        self._first_send_done = False
        self._logger.debug("dtmf_handler_reset_for_new_response")

    @property
    def pending_task_count(self) -> int:
        """Get the number of pending DTMF send tasks.

        Returns:
            Count of tasks still in progress
        """
        return len(self._pending_tasks)

    @property
    def sent_sequences(self) -> set[str]:
        """Get the set of sent sequence keys.

        Returns:
            Set of occurrence_key values for sent sequences
        """
        return self._sent_sequences.copy()
