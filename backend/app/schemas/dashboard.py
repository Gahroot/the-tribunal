"""Dashboard statistics schemas."""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Core dashboard statistics."""

    total_contacts: int
    active_campaigns: int
    calls_today: int
    messages_sent: int
    # Change percentages (compared to previous period)
    contacts_change: str
    campaigns_change: str
    calls_change: str
    messages_change: str


class RecentActivity(BaseModel):
    """Recent activity item."""

    id: str
    type: str  # call, sms, campaign, booking
    contact: str
    initials: str
    action: str
    time: str
    duration: str | None = None


class CampaignStat(BaseModel):
    """Campaign statistics for dashboard."""

    id: str
    name: str
    type: str  # sms, voice, email
    progress: int
    sent: int
    total: int
    status: str


class AgentStat(BaseModel):
    """Agent statistics for dashboard."""

    id: str
    name: str
    calls: int
    messages: int
    success_rate: int


class TodayOverview(BaseModel):
    """Today's overview metrics."""

    completed: int
    pending: int
    failed: int


class AppointmentStats(BaseModel):
    """Appointment performance metrics for the dashboard."""

    appointments_today: int
    appointments_this_week: int
    show_up_rate_30d: float | None  # null when fewer than 5 completed+no_show in window
    no_shows_30d: int
    completed_30d: int


class DashboardResponse(BaseModel):
    """Complete dashboard response."""

    stats: DashboardStats
    recent_activity: list[RecentActivity]
    campaign_stats: list[CampaignStat]
    agent_stats: list[AgentStat]
    today_overview: TodayOverview
    appointment_stats: AppointmentStats
