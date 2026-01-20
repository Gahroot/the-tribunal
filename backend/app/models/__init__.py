"""Database models."""

from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.automation import Automation
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_number_pool import CampaignNumberPool
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.invitation import WorkspaceInvitation
from app.models.lead_magnet import LeadMagnet
from app.models.message_test import (
    MessageTest,
    MessageTestStatus,
    TestContact,
    TestContactStatus,
    TestVariant,
)
from app.models.offer import Offer
from app.models.offer_lead_magnet import OfferLeadMagnet
from app.models.opportunity import Opportunity, OpportunityActivity, OpportunityLineItem
from app.models.opt_out import GlobalOptOut
from app.models.phone_number import PhoneNumber
from app.models.phone_number_stats import PhoneNumberDailyStats
from app.models.pipeline import Pipeline, PipelineStage
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceIntegration, WorkspaceMembership

__all__ = [
    "User",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceIntegration",
    "WorkspaceInvitation",
    "Contact",
    "Conversation",
    "Message",
    "Agent",
    "Campaign",
    "CampaignContact",
    "CampaignNumberPool",
    "Appointment",
    "PhoneNumber",
    "PhoneNumberDailyStats",
    "GlobalOptOut",
    "Offer",
    "LeadMagnet",
    "OfferLeadMagnet",
    "Automation",
    "Pipeline",
    "PipelineStage",
    "Opportunity",
    "OpportunityLineItem",
    "OpportunityActivity",
    "MessageTest",
    "MessageTestStatus",
    "TestVariant",
    "TestContact",
    "TestContactStatus",
]
