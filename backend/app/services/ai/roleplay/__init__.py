"""Practice-arena roleplay services.

Drives a synthetic prospect LLM against a configured agent's *real* prompt so
operators can rehearse and score conversations before any real lead is touched.

Distinct from ``app.services.ai.testing`` (internal IVR-menu navigation): here
the simulated counterparty is a believable buyer/lead, not a phone menu.
"""

from app.services.ai.roleplay.default_personas import DEFAULT_PERSONAS, DefaultPersona
from app.services.ai.roleplay.roleplay_service import RoleplayService

__all__ = [
    "DEFAULT_PERSONAS",
    "DefaultPersona",
    "RoleplayService",
]
