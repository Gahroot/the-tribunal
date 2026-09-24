"""CRM assistant tool definitions for OpenAI function calling.

Style: short imperative descriptions, only non-obvious params documented.
Mirrors the prompt-hint style in ezcoder's tools/prompt-hints.ts.
"""

from copy import deepcopy
from typing import Any

from app.services.ai.crm_assistant._tool_metadata import get_tool_policy
from app.services.ai.tool_definitions import tools_for_channel

CONFIRMED_PARAM = {
    "type": "boolean",
    "description": "True only after explicit user confirmation",
}


def _with_confirmation_property(tool: dict[str, Any]) -> dict[str, Any]:
    """Add the confirmation parameter when tool metadata requires it."""

    function = tool["function"]
    if not get_tool_policy(function["name"]).requires_confirmation:
        return tool
    properties = function.setdefault("parameters", {}).setdefault("properties", {})
    properties.setdefault("confirmed", CONFIRMED_PARAM)
    return tool


def _apply_tool_policy_metadata(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return OpenAI tool definitions augmented from CRM tool metadata."""

    return [_with_confirmation_property(deepcopy(tool)) for tool in tools]


CRM_TOOLS: list[dict[str, Any]] = [tool.render("openai") for tool in tools_for_channel("crm")]


def get_crm_tools() -> list[dict[str, Any]]:
    """Return the CRM tool definitions for OpenAI function calling."""
    return _apply_tool_policy_metadata(CRM_TOOLS)
