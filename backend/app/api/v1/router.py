"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    appointments,
    auth,
    automations,
    call_feedback,
    call_outcomes,
    calls,
    campaigns,
    contacts,
    conversations,
    dashboard,
    demo,
    embed,
    find_leads_ai,
    integrations,
    invitations,
    lead_magnets,
    message_templates,
    message_tests,
    offers,
    opportunities,
    phone_numbers,
    prompt_versions,
    scraping,
    settings,
    voice_campaigns,
    workspaces,
)

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["Workspaces"])
api_router.include_router(
    contacts.router,
    prefix="/workspaces/{workspace_id}/contacts",
    tags=["Contacts"],
)
api_router.include_router(
    conversations.router,
    prefix="/workspaces/{workspace_id}/conversations",
    tags=["Conversations"],
)
api_router.include_router(
    agents.router,
    prefix="/workspaces/{workspace_id}/agents",
    tags=["Agents"],
)
api_router.include_router(
    prompt_versions.router,
    prefix="/workspaces/{workspace_id}/agents/{agent_id}/prompts",
    tags=["Prompt Versions"],
)
api_router.include_router(
    campaigns.router,
    prefix="/workspaces/{workspace_id}/campaigns",
    tags=["Campaigns"],
)
api_router.include_router(
    voice_campaigns.router,
    prefix="/workspaces/{workspace_id}/voice-campaigns",
    tags=["Voice Campaigns"],
)
api_router.include_router(
    message_tests.router,
    prefix="/workspaces/{workspace_id}/message-tests",
    tags=["Message Tests"],
)
api_router.include_router(
    message_templates.router,
    prefix="/workspaces/{workspace_id}/message-templates",
    tags=["Message Templates"],
)
api_router.include_router(
    offers.router,
    prefix="/workspaces/{workspace_id}/offers",
    tags=["Offers"],
)
api_router.include_router(
    lead_magnets.router,
    prefix="/workspaces/{workspace_id}/lead-magnets",
    tags=["Lead Magnets"],
)
api_router.include_router(
    phone_numbers.router,
    prefix="/workspaces/{workspace_id}/phone-numbers",
    tags=["Phone Numbers"],
)
api_router.include_router(
    appointments.router,
    prefix="/workspaces/{workspace_id}/appointments",
    tags=["Appointments"],
)
api_router.include_router(
    calls.router,
    prefix="/workspaces/{workspace_id}/calls",
    tags=["Voice Calls"],
)
api_router.include_router(
    call_outcomes.router,
    prefix="/workspaces/{workspace_id}/calls/{message_id}/outcome",
    tags=["Call Outcomes"],
)
api_router.include_router(
    call_feedback.router,
    prefix="/workspaces/{workspace_id}/calls/{message_id}/feedback",
    tags=["Call Feedback"],
)
api_router.include_router(
    automations.router,
    prefix="/workspaces/{workspace_id}/automations",
    tags=["Automations"],
)
api_router.include_router(
    opportunities.router,
    prefix="/workspaces/{workspace_id}/opportunities",
    tags=["Opportunities"],
)
api_router.include_router(
    dashboard.router,
    prefix="/workspaces/{workspace_id}/dashboard",
    tags=["Dashboard"],
)
api_router.include_router(
    integrations.router,
    prefix="/workspaces/{workspace_id}/integrations",
    tags=["Integrations"],
)
api_router.include_router(
    invitations.router,
    prefix="/workspaces/{workspace_id}/invitations",
    tags=["Invitations"],
)
api_router.include_router(
    scraping.router,
    prefix="/workspaces/{workspace_id}/scraping",
    tags=["Lead Scraping"],
)
api_router.include_router(
    find_leads_ai.router,
    prefix="/workspaces/{workspace_id}/find-leads-ai",
    tags=["Find Leads AI"],
)
# Public invitation endpoints (token-based)
api_router.include_router(
    invitations.public_router,
    prefix="/invitations",
    tags=["Invitations"],
)
# Public offer endpoints (no auth)
api_router.include_router(
    offers.public_router,
    prefix="/p/offers",
    tags=["Public Offers"],
)
# Public demo endpoints (no auth, rate limited)
api_router.include_router(
    demo.router,
    prefix="/p/demo",
    tags=["Public Demo"],
)
# Public embed endpoints (no auth, origin-validated)
api_router.include_router(
    embed.router,
    prefix="/p/embed",
    tags=["Public Embed"],
)
