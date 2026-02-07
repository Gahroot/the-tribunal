"""IVR (Interactive Voice Response) detection package.

This package provides IVR detection capabilities for voice agents:
- IVR menus vs human conversation using rule-based classification
- IVR loops using TF-IDF transcript similarity
- DTMF tags in agent responses for automated navigation

Usage:
    from app.services.ai.ivr import IVRDetector, IVRDetectorConfig, IVRMode

    detector = IVRDetector(
        config=IVRDetectorConfig(),
        on_mode_change=lambda old, new: print(f"Mode: {old} -> {new}"),
    )
    mode = await detector.process_transcript("Press 1 for sales", is_agent=False)
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
    # Types & enums
    "DTMFContext",
    "IVRDetectorConfig",
    "IVRMenuState",
    "IVRMode",
    "IVRStatus",
    # Classifier
    "IVRClassifier",
    # Loop detection
    "LoopDetector",
    # DTMF
    "DTMFParser",
    "DTMFValidator",
    # Orchestrator
    "IVRDetector",
]
