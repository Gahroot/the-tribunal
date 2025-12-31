"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import agents, auth, campaigns, contacts, conversations, offers, phone_numbers, workspaces

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
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
    offers.router,
    prefix="/workspaces/{workspace_id}/offers",
    tags=["Offers"],
)
api_router.include_router(
    phone_numbers.router,
    prefix="/workspaces/{workspace_id}/phone-numbers",
    tags=["Phone Numbers"],
)
