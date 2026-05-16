# CRM Assistant Agent — Personal AI Agent for CRM Management

## Overview

Build a "Copilot Agent" — a special agent type that the workspace owner can interact with via **SMS** and an **in-app chat panel** to perform any CRM operation. Unlike existing agents that talk to *contacts*, this agent talks to *you* (the CRM operator) and executes CRM functions on your behalf.

**Key concept:** This reuses the existing Agent model but introduces a new `agent_type` field (`"crm_assistant"`) that changes the agent's behavior: instead of responding to contacts, it responds to the operator and has access to a rich set of CRM operation tools.

## Architecture

### How It Fits Into Existing System

The CRM assistant piggybacks on the existing text agent pipeline:

```
User texts their CRM number
  → Telnyx webhook (handle_inbound_message)
  → Command processor checks for Y/N commands (unchanged)
  → NEW: CRM assistant command router intercepts messages from known operator numbers
  → process_inbound_for_operator() — new flow
     → Builds context (workspace state, recent activity)
     → Calls LLM with CRM operation tools
     → Executes tool calls (create_contact, start_campaign, etc.)
     → Responds via SMS
```

The in-app chat uses a dedicated API endpoint (`POST /workspaces/{id}/assistant/chat`) that calls the same processing logic.

### New Components

| Layer | File | Purpose |
|-------|------|---------|
| **Model** | `backend/app/models/agent.py` | Add `agent_type` column (default `"customer_facing"`, new value `"crm_assistant"`) |
| **Migration** | `backend/alembic/versions/xxx_add_agent_type.py` | Add column + seed a default CRM assistant per workspace |
| **Service** | `backend/app/services/ai/crm_assistant/` | New service directory |
| | `_processor.py` | Main orchestrator: receives user message, builds context, calls LLM, executes tools |
| | `_context_builder.py` | Builds workspace-aware context (active campaigns, recent leads, appointments, etc.) |
| | `_tools.py` | OpenAI function definitions for all CRM operations |
| | `_tool_executor.py` | Executes CRM tool calls by calling existing services/APIs internally |
| **API** | `backend/app/api/v1/crm_assistant.py` | `POST /chat` endpoint for in-app usage |
| **SMS Hook** | Modified `telnyx_message_handlers.py` | Intercept operator messages before normal processing |
| **Frontend API** | `frontend/src/lib/api/crm-assistant.ts` | API client |
| **Frontend Page** | `frontend/src/app/assistant/page.tsx` | Full-page assistant chat view |
| **Frontend Component** | `frontend/src/components/assistant/assistant-chat.tsx` | Chat UI component (reuses conversation-feed patterns) |
| **Sidebar** | Modified `app-sidebar.tsx` | Add "Assistant" nav item |

## CRM Operations (Tools)

The assistant has access to these operations, implemented as OpenAI function calls:

### Contact Management
- `search_contacts` — Search contacts by name, phone, email, tag
- `create_contact` — Create a new contact
- `update_contact` — Update contact fields
- `add_tag_to_contact` / `remove_tag_from_contact` — Tag management

### Campaign Management
- `list_campaigns` — Show active/draft campaigns with stats
- `create_campaign` — Create a new SMS campaign (draft)
- `launch_campaign` — Launch a draft campaign
- `pause_campaign` / `resume_campaign` — Campaign control

### Agent Management
- `list_agents` — Show agents with status
- `create_agent` — Create a new agent with a prompt
- `update_agent_prompt` — Update an agent's system prompt
- `toggle_agent` — Enable/disable an agent

### Communication
- `send_sms` — Send an SMS to a contact
- `get_conversation` — Read recent messages with a contact
- `list_recent_conversations` — Show recent conversations with unread counts

### Appointments
- `check_availability` — Check Cal.com slots
- `book_appointment` — Book for a contact
- `list_appointments` — Show upcoming appointments
- `cancel_appointment` — Cancel an appointment

### Insights
- `get_dashboard_stats` — Current dashboard metrics
- `get_campaign_performance` — Campaign stats with delivery/reply rates

### Opportunity Pipeline
- `list_opportunities` — Show pipeline
- `create_opportunity` — Create a deal/opportunity
- `update_opportunity_stage` — Move through pipeline

## Detailed Design

### 1. Agent Model Changes

Add `agent_type` column to `Agent` model:
```python
agent_type: Mapped[str] = mapped_column(
    String(30), nullable=False, default="customer_facing"
)  # customer_facing, crm_assistant
```

CRM assistant agents are special:
- `channel_mode = "text"` (SMS + in-app)
- No Cal.com config needed (it uses the workspace's Cal.com for booking *for contacts*)
- `enabled_tools` lists the CRM operations, not customer-facing tools
- Has a dedicated system prompt that explains it's a CRM management assistant

### 2. SMS Flow — Operator Detection

In `handle_inbound_message`, after command processing but before normal conversation handling, add operator detection:

```python
# Check if sender is the workspace owner/operator
is_operator = await crm_assistant_router.try_route(
    db=db, from_number=from_number, to_number=to_number, body=body,
)
if is_operator:
    return  # Message consumed by assistant
```

The router identifies operators by checking `HumanProfile.phone_number` or `User.phone_number` against the workspace. If the sender is a known operator and a CRM assistant agent exists for the workspace, it routes to the assistant.

### 3. CRM Assistant Processor

```python
# backend/app/services/ai/crm_assistant/_processor.py

async def process_operator_message(
    workspace_id: UUID,
    user_id: int,
    message: str,
    db: AsyncSession,
    response_channel: Literal["sms", "in_app"] = "in_app",
    sms_reply_to: str | None = None,  # Phone number to reply to via SMS
) -> str:
    """Process a message from the CRM operator and return the assistant's response."""

    # 1. Get the workspace's CRM assistant agent
    agent = await _get_crm_assistant(db, workspace_id)

    # 2. Build workspace context (summary of what's happening)
    context = await build_workspace_context(db, workspace_id)

    # 3. Get or create the operator's conversation thread
    conversation = await _get_or_create_operator_conversation(db, workspace_id, user_id)

    # 4. Build messages with conversation history
    messages = await _build_messages(conversation, context, message, db)

    # 5. Call LLM with CRM tools
    response = await client.chat.completions.create(
        model="gpt-4.1",
        messages=messages,
        tools=crm_tools,
        tool_choice="auto",
    )

    # 6. Handle tool calls in a loop
    while response.choices[0].message.tool_calls:
        tool_results = await execute_crm_tools(db, workspace_id, response.choices[0].message.tool_calls)
        messages.append(response.choices[0].message)
        messages.extend(tool_results)
        response = await client.chat.completions.create(
            model="gpt-4.1", messages=messages, tools=crm_tools,
        )

    # 7. Save message to conversation, send SMS if needed
    ...
```

### 4. CRM Tool Executor

Each CRM tool calls existing services directly — no HTTP API calls needed since we're in the same process:

```python
# backend/app/services/ai/crm_assistant/_tool_executor.py

class CRMToolExecutor:
    def __init__(self, db: AsyncSession, workspace_id: UUID, user_id: int):
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id

    async def execute(self, function_name: str, arguments: dict) -> dict:
        """Dispatch to the appropriate handler."""
        handlers = {
            "search_contacts": self._search_contacts,
            "create_contact": self._create_contact,
            "create_agent": self._create_agent,
            "send_sms": self._send_sms,
            "list_campaigns": self._list_campaigns,
            # ... etc
        }
        handler = handlers.get(function_name)
        if not handler:
            return {"success": False, "error": f"Unknown function: {function_name}"}
        return await handler(arguments)

    async def _search_contacts(self, args: dict) -> dict:
        # Directly queries the Contact model with filters
        ...

    async def _create_agent(self, args: dict) -> dict:
        # Uses existing agent creation logic
        ...
```

### 5. In-App Chat API

```python
# backend/app/api/v1/crm_assistant.py

@router.post("/chat")
async def chat_with_assistant(
    workspace_id: UUID,
    request: AssistantChatRequest,  # { message: str }
    current_user: CurrentUser,
    db: DB,
    workspace: WorkspaceDep,
) -> AssistantChatResponse:  # { response: str, actions_taken: list[ActionSummary] }
    ...
```

### 6. In-App Chat UI

A dedicated page at `/assistant` with:
- Chat message list (mirrors conversation-feed.tsx patterns)
- Input area with send button
- Tool execution results shown inline (e.g., "Created agent 'Sales Bot' ✓")
- Action confirmations for destructive operations

The UI reuses existing primitives: `ScrollArea`, `Button`, `Textarea`, `Avatar` from shadcn/ui.

### 7. Operator Conversation Storage

We need a way to store the operator's conversation history. Options:
- **Reuse `Conversation` model** with a special flag — simplest, but mixes operator and contact conversations
- **New `AssistantConversation` model** — cleanest separation

Recommendation: **New model** to keep it clean. Minimal schema:

```python
class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    id: UUID PK
    workspace_id: UUID FK
    user_id: int FK  # The operator
    agent_id: UUID FK  # The CRM assistant agent
    created_at, updated_at timestamps
    # messages via relationship

class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    id: UUID PK
    conversation_id: UUID FK
    role: str  # "user", "assistant", "tool"
    content: text
    tool_calls: JSONB  # For tool call messages
    tool_call_id: str | None  # For tool result messages
    created_at timestamp
```

## Security & Safety

1. **Operator verification:** Only recognized operator phone numbers (from HumanProfile or User model) can trigger the CRM assistant via SMS
2. **Workspace scoping:** All tool operations are scoped to the workspace — the assistant cannot touch other workspaces
3. **Auth requirement:** In-app chat requires authenticated user with workspace membership
4. **Destructive action confirmation:** Tools like `delete_contact`, `cancel_campaign` require explicit confirmation step (the assistant asks "Are you sure?" before executing)
5. **No access to other users' data:** The assistant operates as the workspace, not as a specific user — but actions are attributed to the requesting user

## System Prompt

The CRM assistant gets a carefully crafted system prompt that:
- Explains it's a CRM management assistant for the workspace
- Lists available operations and when to use them
- Includes current workspace context (active campaigns, recent leads, etc.)
- Instructs it to confirm before destructive operations
- Tells it to be concise and action-oriented in responses

## Implementation Order

The implementation is ordered to build foundational pieces first, then layer on features.

## Steps

1. Add `agent_type` column to `backend/app/models/agent.py` and create Alembic migration
2. Create `AssistantConversation` and `AssistantMessage` models in `backend/app/models/assistant_conversation.py` with Alembic migration
3. Create CRM assistant tool definitions in `backend/app/services/ai/crm_assistant/_tools.py` (all OpenAI function schemas)
4. Create CRM assistant tool executor in `backend/app/services/ai/crm_assistant/_tool_executor.py` (handlers that call existing services)
5. Create workspace context builder in `backend/app/services/ai/crm_assistant/_context_builder.py`
6. Create main processor in `backend/app/services/ai/crm_assistant/_processor.py` (orchestrates LLM calls + tool execution loop)
7. Create `__init__.py` with public API for the crm_assistant service package
8. Create backend API endpoint `backend/app/api/v1/crm_assistant.py` with POST /chat route and register in router.py
9. Modify `backend/app/api/webhooks/telnyx_message_handlers.py` to detect operator SMS and route to CRM assistant
10. Create schemas in `backend/app/schemas/crm_assistant.py` (ChatRequest, ChatResponse, ActionSummary)
11. Create frontend API client `frontend/src/lib/api/crm-assistant.ts`
12. Create frontend assistant chat component `frontend/src/components/assistant/assistant-chat.tsx`
13. Create frontend assistant page `frontend/src/app/assistant/page.tsx`
14. Add "Assistant" nav item to sidebar in `frontend/src/components/layout/app-sidebar.tsx`
15. Add React Query hook `frontend/src/hooks/useAssistant.ts` for chat mutations
16. Add query keys for assistant to `frontend/src/lib/query-keys.ts`
17. Run linter and type checks on all modified files, fix any errors
