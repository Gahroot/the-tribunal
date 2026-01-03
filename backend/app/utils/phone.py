"""Phone number utilities for E.164 normalization and validation."""

import phonenumbers
import structlog

logger = structlog.get_logger()

DEFAULT_COUNTRY = "US"


class PhoneNumberError(ValueError):
    """Raised when phone number validation/normalization fails."""


def normalize_phone_e164(phone_input: str, country: str = DEFAULT_COUNTRY) -> str:
    """Normalize phone number to E.164 format.

    Args:
        phone_input: Phone number in any format
        country: Country code for parsing (default: US)

    Returns:
        Phone number in E.164 format (e.g., "+15551234567")

    Raises:
        PhoneNumberError: If phone number is invalid
    """
    if not phone_input or not phone_input.strip():
        raise PhoneNumberError("Phone number cannot be empty")

    try:
        parsed = phonenumbers.parse(phone_input, country)

        if not phonenumbers.is_valid_number(parsed):
            raise PhoneNumberError(f"Invalid phone number: {phone_input}")

        if not phonenumbers.is_possible_number(parsed):
            raise PhoneNumberError(f"Impossible phone number: {phone_input}")

        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    except phonenumbers.NumberParseException as e:
        raise PhoneNumberError(f"Cannot parse phone number '{phone_input}': {e}") from e


def validate_phone_number(phone_input: str, country: str = DEFAULT_COUNTRY) -> bool:
    """Validate if a phone number is valid."""
    try:
        parsed = phonenumbers.parse(phone_input, country)
        return phonenumbers.is_valid_number(parsed) and phonenumbers.is_possible_number(parsed)
    except phonenumbers.NumberParseException:
        return False


def normalize_phone_safe(phone_input: str, country: str = DEFAULT_COUNTRY) -> str | None:
    """Safely normalize phone number, returning None on failure."""
    try:
        return normalize_phone_e164(phone_input, country)
    except PhoneNumberError:
        return None
