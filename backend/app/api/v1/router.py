"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    appointments,
    auth,
    automations,
    calls,
    campaigns,
    contacts,
    conversations,
    dashboard,
    lead_magnets,
    offers,
    opportunities,
    phone_numbers,
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
