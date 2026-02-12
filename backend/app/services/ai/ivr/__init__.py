"""IVR (Interactive Voice Response) detection and navigation package.

This package provides IVR detection and navigation capabilities for voice agents:
- IVR menus vs human conversation using rule-based classification
- IVR loops using TF-IDF transcript similarity
- DTMF tags in agent responses for automated navigation
- Phase 1 IVR gate for 2-phase calling (cheap transcription before AI)

Usage:
    from app.services.ai.ivr import IVRDetector, IVRDetectorConfig, IVRMode

    detector = IVRDetector(
        config=IVRDetectorConfig(),
        on_mode_change=lambda old, new: print(f"Mode: {old} -> {new}"),
    )
    mode = await detector.process_transcript("Press 1 for sales", is_agent=False)

    # Phase 1 gate for 2-phase calling:
    from app.services.ai.ivr import IVRGate, GateOutcome

    gate = IVRGate(call_control_id="...", navigation_goal="Reach a human")
    result = await gate.run(websocket)
"""

from app.services.ai.ivr.classifier import IVRClassifier as IVRClassifier
from app.services.ai.ivr.detector import IVRDetector as IVRDetector
from app.services.ai.ivr.dtmf import DTMFParser as DTMFParser
from app.services.ai.ivr.dtmf import DTMFValidator as DTMFValidator
from app.services.ai.ivr.gate import GateOutcome as GateOutcome
from app.services.ai.ivr.gate import GateResult as GateResult
from app.services.ai.ivr.gate import IVRGate as IVRGate
from app.services.ai.ivr.loop_detector import LoopDetector as LoopDetector
from app.services.ai.ivr.navigator import ScriptedNavigator as ScriptedNavigator
from app.services.ai.ivr.transcriber import WhisperTranscriber as WhisperTranscriber
from app.services.ai.ivr.types import DTMFContext as DTMFContext
from app.services.ai.ivr.types import IVRDetectorConfig as IVRDetectorConfig
from app.services.ai.ivr.types import IVRMenuState as IVRMenuState
from app.services.ai.ivr.types import IVRMode as IVRMode
from app.services.ai.ivr.types import IVRStatus as IVRStatus

__all__ = [
    # Types & enums
    "DTMFContext",
    "GateOutcome",
    "GateResult",
    "IVRDetectorConfig",
    "IVRMenuState",
    "IVRMode",
    "IVRStatus",
    # Classifier
    "IVRClassifier",
    # Gate (Phase 1)
    "IVRGate",
    # Loop detection
    "LoopDetector",
    # Navigator
    "ScriptedNavigator",
    # DTMF
    "DTMFParser",
    "DTMFValidator",
    # Orchestrator
    "IVRDetector",
    # Transcriber
    "WhisperTranscriber",
]
