"""Strategy classes for generating individual nudge types."""

from app.services.nudges.strategies.anniversary import AnniversaryNudgeStrategy
from app.services.nudges.strategies.base import NudgeContext, NudgeStrategy
from app.services.nudges.strategies.birthday import BirthdayNudgeStrategy
from app.services.nudges.strategies.cooling import CoolingNudgeStrategy
from app.services.nudges.strategies.custom_date import CustomDateNudgeStrategy
from app.services.nudges.strategies.deal_stall import DealStallNudgeStrategy
from app.services.nudges.strategies.follow_up import FollowUpNudgeStrategy
from app.services.nudges.strategies.hot_lead import HotLeadNudgeStrategy
from app.services.nudges.strategies.noshow_recovery import NoShowRecoveryNudgeStrategy
from app.services.nudges.strategies.referral_ask import ReferralAskNudgeStrategy
from app.services.nudges.strategies.unresponsive import UnresponsiveNudgeStrategy

__all__ = [
    "AnniversaryNudgeStrategy",
    "BirthdayNudgeStrategy",
    "CoolingNudgeStrategy",
    "CustomDateNudgeStrategy",
    "DealStallNudgeStrategy",
    "FollowUpNudgeStrategy",
    "HotLeadNudgeStrategy",
    "NoShowRecoveryNudgeStrategy",
    "NudgeContext",
    "NudgeStrategy",
    "ReferralAskNudgeStrategy",
    "UnresponsiveNudgeStrategy",
]
