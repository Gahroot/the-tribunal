"""Voice agent exception hierarchy.

This module defines custom exceptions for voice agent operations,
following the pattern established in calcom.py for consistent
error handling across the application.

Exception Hierarchy:
    VoiceAgentError (base)
    ├── VoiceAgentConnectionError - Connection failures
    ├── VoiceAgentConfigurationError - Invalid configuration
    ├── VoiceAgentTimeoutError - Operation timeouts
    ├── VoiceAgentAuthError - Authentication failures
    └── VoiceAgentProviderError - Provider-specific errors
"""


class VoiceAgentError(Exception):
    """Base exception for voice agent errors.

    All voice agent-related exceptions should inherit from this class
    to enable consistent error handling at the voice bridge level.
    """

    def __init__(self, message: str, provider: str | None = None) -> None:
        """Initialize voice agent error.

        Args:
            message: Human-readable error message
            provider: Voice provider name (openai, grok, elevenlabs)
        """
        self.message = message
        self.provider = provider
        super().__init__(message)

    def __str__(self) -> str:
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message


class VoiceAgentConnectionError(VoiceAgentError):
    """Error connecting to voice provider API.

    Raised when:
    - WebSocket connection fails
    - Network connectivity issues
    - Provider service is unavailable
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        status_code: int | None = None,
    ) -> None:
        """Initialize connection error.

        Args:
            message: Error message
            provider: Voice provider name
            status_code: HTTP/WebSocket status code if available
        """
        super().__init__(message, provider)
        self.status_code = status_code


class VoiceAgentConfigurationError(VoiceAgentError):
    """Error in voice agent configuration.

    Raised when:
    - API key is missing or invalid
    - Invalid voice ID specified
    - Required settings are missing
    - Incompatible configuration options
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        config_key: str | None = None,
    ) -> None:
        """Initialize configuration error.

        Args:
            message: Error message
            provider: Voice provider name
            config_key: The specific configuration key that's invalid
        """
        super().__init__(message, provider)
        self.config_key = config_key


class VoiceAgentTimeoutError(VoiceAgentError):
    """Timeout waiting for voice provider response.

    Raised when:
    - Connection attempt times out
    - Tool execution exceeds timeout
    - Response generation takes too long
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        timeout_seconds: float | None = None,
        operation: str | None = None,
    ) -> None:
        """Initialize timeout error.

        Args:
            message: Error message
            provider: Voice provider name
            timeout_seconds: The timeout value that was exceeded
            operation: The operation that timed out (e.g., "connect", "tool_call")
        """
        super().__init__(message, provider)
        self.timeout_seconds = timeout_seconds
        self.operation = operation


class VoiceAgentAuthError(VoiceAgentError):
    """Authentication error with voice provider API.

    Raised when:
    - API key is invalid or expired
    - API key lacks required permissions
    - Authentication token refresh fails
    """

    pass


class VoiceAgentProviderError(VoiceAgentError):
    """Provider-specific error from voice API.

    Raised when the provider returns an error that doesn't fit
    other categories. Captures the original error details.
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        error_type: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize provider error.

        Args:
            message: Error message
            provider: Voice provider name
            error_type: Provider's error type classification
            error_code: Provider's error code
        """
        super().__init__(message, provider)
        self.error_type = error_type
        self.error_code = error_code


class VoiceAgentToolError(VoiceAgentError):
    """Error during tool execution in voice agent.

    Raised when:
    - Tool callback is not set but tool call received
    - Tool execution fails
    - Tool result submission fails
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        tool_name: str | None = None,
        call_id: str | None = None,
    ) -> None:
        """Initialize tool error.

        Args:
            message: Error message
            provider: Voice provider name
            tool_name: Name of the tool that failed
            call_id: The function call ID from the provider
        """
        super().__init__(message, provider)
        self.tool_name = tool_name
        self.call_id = call_id


class AudioConversionError(Exception):
    """Error during audio format conversion.

    Raised when:
    - Invalid audio data received
    - Conversion between formats fails
    - Sample rate conversion fails
    """

    def __init__(
        self,
        message: str,
        source_format: str | None = None,
        target_format: str | None = None,
    ) -> None:
        """Initialize audio conversion error.

        Args:
            message: Error message
            source_format: Source audio format (e.g., "mulaw_8k", "pcm16_24k")
            target_format: Target audio format
        """
        self.message = message
        self.source_format = source_format
        self.target_format = target_format
        super().__init__(message)
