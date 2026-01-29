"""Call outcome classifier for determining call status from hangup causes."""

from dataclasses import dataclass


@dataclass
class CallClassificationResult:
    """Result of classifying a call outcome.

    Attributes:
        outcome: Call outcome (no_answer, busy, rejected, voicemail, completed, None)
        message_status: Message status to set (failed, completed)
        is_rejection: Whether this was detected as a rejection
    """

    outcome: str | None
    message_status: str
    is_rejection: bool = False


class CallOutcomeClassifier:
    """Classifies call outcomes based on hangup cause and call metadata.

    Maps Telnyx hangup causes to semantic outcomes for campaign tracking
    and SMS fallback triggering.
    """

    # Threshold for detecting rejected calls (quick hangup by callee)
    REJECTED_CALL_THRESHOLD_SECS = 15

    # Very short calls with normal clearing = likely no real conversation
    MINIMAL_CALL_THRESHOLD_SECS = 5

    # Hangup causes that indicate no answer
    NO_ANSWER_CAUSES = frozenset({"NO_ANSWER", "TIMEOUT", "ORIGINATOR_CANCEL"})

    # Hangup causes that indicate user is busy
    BUSY_CAUSES = frozenset({"USER_BUSY"})

    # Hangup causes that indicate explicit rejection
    REJECTION_CAUSES = frozenset({"CALL_REJECTED"})

    # Normal clearing causes (need additional context to classify)
    NORMAL_CLEARING_CAUSES = frozenset({"NORMAL_CLEARING", "NORMAL_RELEASE"})

    def classify(
        self,
        hangup_cause: str,
        duration_secs: int,
        hangup_source: str,
        booking_outcome: str | None = None,
    ) -> CallClassificationResult:
        """Classify a call outcome based on hangup cause and call metadata.

        Args:
            hangup_cause: Telnyx hangup cause (e.g., NO_ANSWER, USER_BUSY)
            duration_secs: Call duration in seconds
            hangup_source: Who hung up (e.g., "callee", "caller")
            booking_outcome: Optional booking outcome (e.g., "success")

        Returns:
            CallClassificationResult with outcome, message_status, and is_rejection
        """
        # Normalize hangup cause to uppercase
        hangup_cause = hangup_cause.upper() if hangup_cause else ""

        # Detect rejected call: callee hung up quickly without meaningful conversation
        is_rejected_call = (
            duration_secs < self.REJECTED_CALL_THRESHOLD_SECS
            and hangup_cause in self.NORMAL_CLEARING_CAUSES
            and hangup_source == "callee"
        )

        # Determine call outcome based on hangup cause
        call_outcome: str | None = None
        message_status = "completed"  # Default to completed

        if hangup_cause in self.NO_ANSWER_CAUSES:
            call_outcome = "no_answer"
            message_status = "failed"
        elif hangup_cause in self.BUSY_CAUSES:
            call_outcome = "busy"
            message_status = "failed"
        elif hangup_cause in self.REJECTION_CAUSES or is_rejected_call:
            call_outcome = "rejected"
            message_status = "failed"
        elif (
            duration_secs < self.MINIMAL_CALL_THRESHOLD_SECS
            and hangup_cause in self.NORMAL_CLEARING_CAUSES
        ):
            # Very short call with normal clearing = likely no real conversation
            call_outcome = "no_answer"
            message_status = "failed"

        # If booking was successful, override failed status
        if booking_outcome == "success" and message_status == "failed":
            message_status = "completed"

        return CallClassificationResult(
            outcome=call_outcome,
            message_status=message_status,
            is_rejection=is_rejected_call,
        )

    def classify_machine_detection(self, result_type: str) -> str | None:
        """Classify machine detection result.

        Args:
            result_type: Detection result (human, machine, fax, silence)

        Returns:
            Call outcome if machine/fax detected, None otherwise
        """
        if result_type in ("machine", "fax"):
            return "voicemail"
        return None
