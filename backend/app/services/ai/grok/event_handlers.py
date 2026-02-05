"""Event handlers for Grok Realtime API events.

This module provides a registry-based approach to handling WebSocket events
from the Grok Realtime API. Instead of a monolithic if/elif chain, each
event type has its own handler class that can be tested independently.
"""

import base64
import binascii
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class EventContext:
    """Context passed to event handlers.

    Contains state and callbacks needed by handlers to process events.

    Attributes:
        is_interrupted: Whether audio is currently interrupted (barge-in)
        append_agent_transcript: Callback to append transcript delta
        add_user_transcript: Callback to add completed user transcript
        handle_speech_started: Callback for barge-in handling
        handle_response_created: Callback for new response
        handle_response_done: Callback for response completion
        handle_function_call: Callback for function call execution
        cancel_response: Callback to cancel current response
        check_dtmf_tags: Callback to check for DTMF tags
        process_ivr_transcript: Callback to process IVR transcript
        handle_ivr_mode_switch: Callback for IVR mode changes
        ivr_detector: IVR detector instance (if enabled)
        ivr_mode: Current IVR mode
    """

    is_interrupted: Callable[[], bool]
    append_agent_transcript: Callable[[str], None]
    add_user_transcript: Callable[[str], None]
    handle_speech_started: Callable[[], None]
    handle_response_created: Callable[[], None]
    handle_response_done: Callable[[str], None]
    handle_function_call: Callable[[dict[str, Any]], Any]
    cancel_response: Callable[[], Any]
    check_dtmf_tags: Callable[[str], Any]
    process_ivr_transcript: Callable[[str, bool], Any]
    handle_ivr_mode_switch: Callable[[Any, Any], Any]
    ivr_detector: Any | None = None
    ivr_mode: Any | None = None
    agent_transcript: Callable[[], str] | None = None


@dataclass
class HandlerResult:
    """Result from an event handler.

    Attributes:
        audio_chunks: Audio bytes to yield (if any)
        should_continue: Whether to continue processing events
        state_updates: Any state updates to apply
    """

    audio_chunks: list[bytes] = field(default_factory=list)
    should_continue: bool = True
    state_updates: dict[str, Any] = field(default_factory=dict)


class EventHandler(ABC):
    """Base class for event handlers.

    Each handler processes a specific event type from the Grok Realtime API.
    """

    def __init__(self) -> None:
        """Initialize the handler."""
        self._logger = logger.bind(service=f"event_handler_{self.event_type}")

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Return the event type this handler processes."""
        ...

    @abstractmethod
    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle the event.

        Args:
            event: The event dictionary from Grok
            context: Event context with callbacks and state

        Returns:
            Handler result with any audio to yield and state updates
        """
        ...


class AudioDeltaHandler(EventHandler):
    """Handler for response.audio.delta and response.output_audio.delta events.

    Decodes base64 audio and yields PCM chunks, respecting interruption state.
    """

    def __init__(self, event_type: str = "response.audio.delta") -> None:
        """Initialize with the specific event type.

        Args:
            event_type: Either "response.audio.delta" or "response.output_audio.delta"
        """
        self._event_type = event_type
        super().__init__()

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return self._event_type

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle audio delta event.

        Args:
            event: Audio delta event
            context: Event context

        Returns:
            Result with decoded audio chunks
        """
        result = HandlerResult()

        # Skip if interrupted
        if context.is_interrupted():
            return result

        audio_data = event.get("delta", "")
        if not audio_data:
            return result

        try:
            decoded = base64.b64decode(audio_data)
            result.audio_chunks.append(decoded)
        except (binascii.Error, ValueError) as e:
            self._logger.warning(
                "invalid_base64_audio",
                error=str(e),
            )

        return result


class TranscriptDeltaHandler(EventHandler):
    """Handler for transcript delta events.

    Handles:
    - response.audio_transcript.delta
    - response.output_audio_transcript.delta
    - response.text.delta
    """

    def __init__(self, event_type: str = "response.audio_transcript.delta") -> None:
        """Initialize with the specific event type.

        Args:
            event_type: The transcript event type to handle
        """
        self._event_type = event_type
        super().__init__()

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return self._event_type

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle transcript delta event.

        Args:
            event: Transcript delta event
            context: Event context

        Returns:
            Result with state updates
        """
        result = HandlerResult()

        transcript = event.get("delta", "")
        if not transcript:
            return result

        # Append to agent transcript
        context.append_agent_transcript(transcript)

        # Get full transcript for DTMF check
        full_transcript = ""
        if context.agent_transcript:
            full_transcript = context.agent_transcript()

        self._logger.debug(
            "agent_transcript_delta",
            delta=transcript,
            full_length=len(full_transcript),
        )

        # Check for DTMF tags
        if full_transcript:
            await context.check_dtmf_tags(full_transcript)

            # Process through IVR detector if enabled
            if context.ivr_detector:
                await context.process_ivr_transcript(full_transcript, True)

        return result


class UserTranscriptHandler(EventHandler):
    """Handler for completed user transcripts.

    Handles conversation.item.input_audio_transcription.completed events.
    """

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "conversation.item.input_audio_transcription.completed"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle user transcript completion.

        Args:
            event: Transcription completed event
            context: Event context

        Returns:
            Result (may trigger IVR mode switch)
        """
        result = HandlerResult()

        user_text = event.get("transcript", "")
        if not user_text:
            return result

        context.add_user_transcript(user_text)

        # Process through IVR detector if enabled
        if context.ivr_detector:
            old_mode = context.ivr_mode
            new_mode = await context.process_ivr_transcript(user_text, False)
            if new_mode != old_mode:
                await context.handle_ivr_mode_switch(old_mode, new_mode)

        return result


class ResponseDoneHandler(EventHandler):
    """Handler for response.done events.

    Processes completed responses and any function calls within them.
    """

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "response.done"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle response completion.

        Args:
            event: Response done event
            context: Event context

        Returns:
            Result with any state updates
        """
        result = HandlerResult()

        response_data = event.get("response", {})
        output_items = response_data.get("output", [])
        response_status = response_data.get("status", "")

        # Handle response completion
        context.handle_response_done(response_status)

        self._logger.info(
            "response_done",
            response_id=response_data.get("id"),
            status=response_status,
            output_item_count=len(output_items),
            output_item_types=[item.get("type") for item in output_items],
        )

        return result


class OutputItemDoneHandler(EventHandler):
    """Handler for response.output_item.done events.

    Processes completed output items including function calls.
    """

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "response.output_item.done"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle output item completion.

        Args:
            event: Output item done event
            context: Event context

        Returns:
            Result
        """
        result = HandlerResult()

        item = event.get("item", {})
        item_type = item.get("type")

        self._logger.debug(
            "output_item_done",
            item_type=item_type,
            item_keys=list(item.keys()),
        )

        if item_type == "function_call":
            self._logger.info(
                "function_call_in_output_item",
                function_name=item.get("name"),
                call_id=item.get("call_id"),
            )
            await context.handle_function_call(item)

        return result


class SpeechStartedHandler(EventHandler):
    """Handler for barge-in detection.

    Handles input_audio_buffer.speech_started events.
    """

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "input_audio_buffer.speech_started"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle speech start (barge-in).

        Args:
            event: Speech started event
            context: Event context

        Returns:
            Result
        """
        result = HandlerResult()

        # Handle barge-in
        context.handle_speech_started()

        # Cancel current response
        await context.cancel_response()

        return result


class SpeechStoppedHandler(EventHandler):
    """Handler for speech stopped events."""

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "input_audio_buffer.speech_stopped"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle speech stop.

        Args:
            event: Speech stopped event
            context: Event context

        Returns:
            Result
        """
        self._logger.debug("user_speech_stopped")
        return HandlerResult()


class ResponseCreatedHandler(EventHandler):
    """Handler for response.created events."""

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "response.created"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle new response created.

        Args:
            event: Response created event
            context: Event context

        Returns:
            Result
        """
        context.handle_response_created()
        return HandlerResult()


class SessionCreatedHandler(EventHandler):
    """Handler for session.created events."""

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "session.created"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle session creation.

        Args:
            event: Session created event
            context: Event context

        Returns:
            Result
        """
        session = event.get("session", {})
        session_tools = session.get("tools", [])

        self._logger.info(
            "session_created",
            session_id=session.get("id"),
            model=session.get("model"),
            voice=session.get("voice"),
            tools=[t.get("name", t.get("type")) for t in session_tools],
            tool_count=len(session_tools),
        )

        return HandlerResult()


class SessionUpdatedHandler(EventHandler):
    """Handler for session.updated events."""

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "session.updated"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle session update.

        Args:
            event: Session updated event
            context: Event context

        Returns:
            Result
        """
        session = event.get("session", {})
        session_tools = session.get("tools", [])

        self._logger.info(
            "session_updated",
            session_id=session.get("id"),
            tools=[t.get("name", t.get("type")) for t in session_tools],
            tool_count=len(session_tools),
        )

        return HandlerResult()


class ErrorHandler(EventHandler):
    """Handler for error events."""

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return "error"

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle error event.

        Args:
            event: Error event
            context: Event context

        Returns:
            Result (continues processing - some errors are recoverable)
        """
        error = event.get("error", {})

        self._logger.error(
            "grok_realtime_error",
            error_type=error.get("type"),
            error_message=error.get("message"),
            error_code=error.get("code"),
            full_error=json.dumps(event),
        )

        # Don't break - some errors are recoverable
        return HandlerResult()


class InformationalEventHandler(EventHandler):
    """Handler for informational events that just need logging.

    Handles:
    - response.output_item.added
    - conversation.item.added
    - response.content_part.added
    - response.content_part.done
    """

    def __init__(self, event_type: str) -> None:
        """Initialize with specific event type.

        Args:
            event_type: The informational event type
        """
        self._event_type = event_type
        super().__init__()

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return self._event_type

    async def handle(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Handle informational event (just log at debug level).

        Args:
            event: The event
            context: Event context

        Returns:
            Empty result
        """
        self._logger.debug(
            "informational_event",
            event_type=self._event_type,
        )
        return HandlerResult()


class EventHandlerRegistry:
    """Registry of event handlers.

    Provides efficient dispatch of events to appropriate handlers.

    Usage:
        registry = EventHandlerRegistry()
        # Handlers are registered automatically

        async for audio_chunk in registry.dispatch_stream(events, context):
            yield audio_chunk
    """

    def __init__(self) -> None:
        """Initialize the registry with default handlers."""
        self._handlers: dict[str, EventHandler] = {}
        self._logger = logger.bind(service="event_handler_registry")
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all default event handlers."""
        # Audio handlers
        self.register(AudioDeltaHandler("response.audio.delta"))
        self.register(AudioDeltaHandler("response.output_audio.delta"))

        # Transcript handlers
        self.register(TranscriptDeltaHandler("response.audio_transcript.delta"))
        self.register(TranscriptDeltaHandler("response.output_audio_transcript.delta"))
        self.register(TranscriptDeltaHandler("response.text.delta"))

        # User transcript
        self.register(UserTranscriptHandler())

        # Response lifecycle
        self.register(ResponseDoneHandler())
        self.register(OutputItemDoneHandler())
        self.register(ResponseCreatedHandler())

        # Speech detection
        self.register(SpeechStartedHandler())
        self.register(SpeechStoppedHandler())

        # Session lifecycle
        self.register(SessionCreatedHandler())
        self.register(SessionUpdatedHandler())

        # Errors
        self.register(ErrorHandler())

        # Informational events
        for event_type in [
            "response.output_item.added",
            "conversation.item.added",
            "response.content_part.added",
            "response.content_part.done",
        ]:
            self.register(InformationalEventHandler(event_type))

    def register(self, handler: EventHandler) -> None:
        """Register an event handler.

        Args:
            handler: The handler to register
        """
        self._handlers[handler.event_type] = handler

    def unregister(self, event_type: str) -> None:
        """Unregister a handler.

        Args:
            event_type: Event type to unregister
        """
        self._handlers.pop(event_type, None)

    def get_handler(self, event_type: str) -> EventHandler | None:
        """Get handler for an event type.

        Args:
            event_type: The event type

        Returns:
            Handler if registered, None otherwise
        """
        return self._handlers.get(event_type)

    async def dispatch(
        self,
        event: dict[str, Any],
        context: EventContext,
    ) -> HandlerResult:
        """Dispatch an event to the appropriate handler.

        Args:
            event: The event to dispatch
            context: Event context

        Returns:
            Handler result
        """
        event_type = event.get("type", "")

        handler = self._handlers.get(event_type)
        if handler:
            return await handler.handle(event, context)

        # Log unknown events
        self._logger.debug(
            "unknown_event",
            event_type=event_type,
            event_keys=list(event.keys()),
        )

        return HandlerResult()

    async def dispatch_stream(
        self,
        events: AsyncIterator[dict[str, Any]],
        context: EventContext,
    ) -> AsyncIterator[bytes]:
        """Dispatch a stream of events, yielding audio chunks.

        Args:
            events: Async iterator of events
            context: Event context

        Yields:
            Audio chunks from handlers
        """
        async for event in events:
            result = await self.dispatch(event, context)

            for chunk in result.audio_chunks:
                yield chunk

            if not result.should_continue:
                break
