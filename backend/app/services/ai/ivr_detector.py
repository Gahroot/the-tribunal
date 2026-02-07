"""Backward-compatibility shim for ivr_detector module.

All classes have been moved to the ``app.services.ai.ivr`` package.
This file re-exports every public symbol so existing imports continue
to work without modification.
"""

from app.services.ai.ivr.classifier import IVRClassifier as IVRClassifier
from app.services.ai.ivr.detector import IVRDetector as IVRDetector
from app.services.ai.ivr.dtmf import DTMFParser as DTMFParser
from app.services.ai.ivr.dtmf import DTMFValidator as DTMFValidator
from app.services.ai.ivr.loop_detector import LoopDetector as LoopDetector
from app.services.ai.ivr.types import DTMFContext as DTMFContext
from app.services.ai.ivr.types import IVRDetectorConfig as IVRDetectorConfig
from app.services.ai.ivr.types import IVRMenuState as IVRMenuState
from app.services.ai.ivr.types import IVRMode as IVRMode
from app.services.ai.ivr.types import IVRStatus as IVRStatus

__all__ = [
    "DTMFContext",
    "DTMFParser",
    "DTMFValidator",
    "IVRClassifier",
    "IVRDetector",
    "IVRDetectorConfig",
    "IVRMenuState",
    "IVRMode",
    "IVRStatus",
    "LoopDetector",
]
