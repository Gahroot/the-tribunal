"""CRM assistant tool definitions for OpenAI function calling."""

from typing import Any

CRM_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": (
                "Search contacts by name, phone number, email, or tag. "
                "Returns matching contacts with their details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term — name, phone, email, or company",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_contact",
            "description": "Create a new CRM contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {
                        "type": "string",
                        "description": "Contact first name",
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Contact last name",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number in E.164 format",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the contact",
                    },
                },
                "required": ["first_name", "phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_campaigns",
            "description": "List campaigns with their status and stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: draft, active, paused, completed",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List AI agents configured in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send an SMS message to a contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "integer",
                        "description": "ID of the contact to message",
                    },
                    "body": {
                        "type": "string",
                        "description": "Message content",
                    },
                },
                "required": ["contact_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_conversation",
            "description": "Read recent messages with a specific contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "integer",
                        "description": "ID of the contact",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent messages to return (default 20)",
                    },
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_conversations",
            "description": "Show recent conversations across all contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_appointments",
            "description": "Show upcoming appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_stats",
            "description": ("Get current dashboard metrics — "
             "contacts, campaigns, messages, appointments."),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_opportunities",
            "description": "Show pipeline opportunities/deals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                    },
                },
            },
        },
    },
]


def get_crm_tools() -> list[dict[str, Any]]:
    """Return the CRM tool definitions for OpenAI function calling."""
    return CRM_TOOLS
