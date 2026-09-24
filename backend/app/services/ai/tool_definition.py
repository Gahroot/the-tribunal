"""Typed tool contracts and provider adapters, independent of execution services."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ToolChannel = Literal["voice", "text", "crm"]
ToolFormat = Literal["openai", "grok", "elevenlabs"]


class ToolArguments(BaseModel):
    """Arguments supplied by a model; unknown fields are never trusted."""

    model_config = ConfigDict(extra="forbid")


def _provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline local model references and omit Pydantic-only presentation details.

    Optional fields may be omitted on the wire. Keeping a single concrete type
    rather than a nullable union preserves the existing realtime tool format.
    Runtime validation still accepts the optional nulls supported by text tools.
    """
    definitions = schema.get("$defs", {})

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            prefix = "#/$defs/"
            reference = value["$ref"]
            if not reference.startswith(prefix):
                raise ValueError(f"Unsupported tool schema reference: {reference}")
            return convert(
                {
                    **definitions[reference[len(prefix) :]],
                    **{key: item for key, item in value.items() if key != "$ref"},
                }
            )
        result = {
            key: (
                {name: convert(prop) for name, prop in item.items()}
                if key == "properties"
                else convert(item)
            )
            for key, item in value.items()
            if key not in {"title", "$defs"} and not (key == "default" and item is None)
        }
        alternatives = result.get("anyOf", [])
        concrete = [item for item in alternatives if item != {"type": "null"}]
        if len(alternatives) == 2 and len(concrete) == 1:
            result.pop("anyOf")
            result.update(concrete[0])
        return result

    return dict(convert(deepcopy(schema)))


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One tool's public schema and gate policy, shared by all providers.

    Gate exemption defaults to false. Exposure remains controlled by each
    session's enabled-tool selection, not by the existence of a definition.
    """

    name: str
    description: str
    arguments: type[ToolArguments]
    channels: frozenset[ToolChannel]
    gate_exempt: bool = False

    def render(
        self,
        provider: ToolFormat,
        *,
        date_context: str | None = None,
    ) -> dict[str, Any]:
        description = self.description
        if date_context is not None:
            description += f" {date_context}"
        function = {
            "name": self.name,
            "description": description,
            "parameters": _provider_schema(self.arguments.model_json_schema()),
        }
        if provider == "openai":
            return {"type": "function", "function": function}
        if provider in {"grok", "elevenlabs"}:
            # ElevenLabs is TTS here; its tool calls run through Grok Realtime.
            return {"type": "function", **function}
        raise ValueError(f"Unsupported tool format: {provider}")
