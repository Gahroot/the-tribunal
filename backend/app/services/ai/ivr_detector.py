"""IVR (Interactive Voice Response) detection module.

This module provides IVR detection capabilities for voice agents based on
patterns from LiveKit, Pipecat, and Bolna. It detects:
- IVR menus vs human conversation using rule-based classification
- IVR loops using TF-IDF transcript similarity
- DTMF tags in agent responses for automated navigation

Usage:
    detector = IVRDetector(
        config=IVRDetectorConfig(),
        on_mode_change=lambda old, new: print(f"Mode: {old} -> {new}"),
        on_loop_detected=lambda: print("Loop detected!"),
        on_dtmf_detected=lambda digits: print(f"DTMF: {digits}"),
    )
    mode = await detector.process_transcript("Press 1 for sales", is_agent=False)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class IVRMode(Enum):
    """Operating mode for voice agent during a call."""

    UNKNOWN = "unknown"
    CONVERSATION = "conversation"  # Normal human conversation
    IVR = "ivr"  # Automated phone menu detected
    VOICEMAIL = "voicemail"  # Voicemail system detected


@dataclass
class IVRDetectorConfig:
    """Configuration for IVR detection behavior.

    Attributes:
        loop_similarity_threshold: TF-IDF similarity threshold for loop detection (0.0-1.0)
        consecutive_classifications: Number of consistent classifications before mode switch
        dtmf_tag_pattern: Regex pattern to extract DTMF digits from agent responses
        max_transcript_history: Maximum transcripts to keep for loop detection
        min_transcript_length: Minimum transcript length to classify (ignore short utterances)
    """

    loop_similarity_threshold: float = 0.85
    consecutive_classifications: int = 2
    dtmf_tag_pattern: str = r"<dtmf>([0-9*#A-Dw]+)</dtmf>"
    max_transcript_history: int = 10
    min_transcript_length: int = 10


@dataclass
class IVRStatus:
    """Current IVR detection status.

    Attributes:
        mode: Current operating mode
        loop_detected: Whether an IVR loop has been detected
        consecutive_ivr_count: Consecutive IVR classifications
        consecutive_human_count: Consecutive human classifications
        last_dtmf_sent: Last DTMF digits detected/sent
    """

    mode: IVRMode = IVRMode.UNKNOWN
    loop_detected: bool = False
    consecutive_ivr_count: int = 0
    consecutive_human_count: int = 0
    last_dtmf_sent: str | None = None


class IVRClassifier:
    """Rule-based classifier for IVR, human, and voicemail detection.

    Uses regex patterns to quickly classify transcripts without API latency.
    Patterns are based on common IVR menu phrases and human speech indicators.
    """

    # IVR menu patterns - phrases that indicate automated phone systems
    IVR_PATTERNS: list[str] = [
        r"press\s+[0-9*#]",
        r"dial\s+[0-9*#]",
        r"for\s+\w+\s*,?\s*press",
        r"to\s+speak\s+\w+\s*,?\s*press",
        r"say\s+or\s+press",
        r"enter\s+your",
        r"please\s+enter",
        r"main\s+menu",
        r"previous\s+menu",
        r"return\s+to\s+the\s+menu",
        r"listen\s+to\s+these\s+options",
        r"following\s+options",
        r"option\s+[0-9]",
        r"extension\s+[0-9]",
        r"if\s+you\s+know\s+your\s+party'?s?\s+extension",
        r"your\s+call\s+is\s+important",
        r"please\s+hold",
        r"all\s+(of\s+)?our\s+(representatives|agents|operators)",
        r"currently\s+(experiencing|assisting)",
        r"hold\s+for\s+the\s+next\s+available",
        r"estimated\s+wait\s+time",
        r"queue\s+position",
        r"thank\s+you\s+for\s+calling",
        r"business\s+hours\s+are",
        r"we\s+are\s+(currently\s+)?closed",
        r"leave\s+a\s+(voice\s*)?message",
        r"at\s+the\s+(tone|beep)",
    ]

    # Human conversation patterns - indicate a real person
    HUMAN_PATTERNS: list[str] = [
        r"how\s+(can|may)\s+i\s+help",
        r"my\s+name\s+is",
        r"this\s+is\s+\w+\s+speaking",
        r"speaking",  # "Hello, this is John speaking"
        r"what\s+can\s+i\s+do\s+for\s+you",
        r"how\s+are\s+you",
        r"good\s+(morning|afternoon|evening)",
        r"thanks\s+for\s+calling",
        r"sorry\s+(about\s+that|to\s+hear)",
        r"let\s+me\s+(check|look|see|help)",
        r"one\s+(moment|second)",
        r"i('ll|'m\s+going\s+to)",
        r"we('ll|'re\s+going\s+to)",
        r"absolutely",
        r"definitely",
        r"no\s+problem",
        r"of\s+course",
    ]

    # Voicemail patterns
    VOICEMAIL_PATTERNS: list[str] = [
        r"leave\s+a\s+(voice\s*)?message",
        r"at\s+the\s+(tone|beep)",
        r"after\s+the\s+(tone|beep)",
        r"record\s+your\s+message",
        r"mailbox\s+(is\s+)?full",
        r"voice\s*mail(\s+box)?",
        r"not\s+available\s+to\s+take\s+your\s+call",
        r"please\s+leave\s+your\s+name\s+and\s+number",
        r"we('ll)?\s+get\s+back\s+to\s+you",
        r"press\s+[0-9*#]\s+to\s+leave\s+a\s+(callback|message)",
    ]

    def __init__(self) -> None:
        """Initialize classifier with compiled regex patterns."""
        self._ivr_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.IVR_PATTERNS
        ]
        self._human_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.HUMAN_PATTERNS
        ]
        self._voicemail_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.VOICEMAIL_PATTERNS
        ]
        self.logger = logger.bind(service="ivr_classifier")

    def classify(self, transcript: str) -> tuple[IVRMode, float]:
        """Classify a transcript as IVR, human, or voicemail.

        Args:
            transcript: Speech transcript to classify

        Returns:
            Tuple of (classification mode, confidence score 0.0-1.0)
        """
        if not transcript or len(transcript.strip()) < 5:
            return IVRMode.UNKNOWN, 0.0

        text = transcript.lower().strip()

        # Count pattern matches
        ivr_matches = sum(1 for p in self._ivr_patterns if p.search(text))
        human_matches = sum(1 for p in self._human_patterns if p.search(text))
        voicemail_matches = sum(1 for p in self._voicemail_patterns if p.search(text))

        total_matches = ivr_matches + human_matches + voicemail_matches

        # Log classification details
        self.logger.debug(
            "ivr_classification",
            transcript_preview=text[:100],
            ivr_matches=ivr_matches,
            human_matches=human_matches,
            voicemail_matches=voicemail_matches,
        )

        # No patterns matched - unknown
        if total_matches == 0:
            return IVRMode.UNKNOWN, 0.0

        # Calculate confidence based on match ratio
        # Higher confidence when one category dominates
        if voicemail_matches > 0 and voicemail_matches >= ivr_matches:
            confidence = min(1.0, voicemail_matches / max(1, total_matches) + 0.2)
            return IVRMode.VOICEMAIL, confidence

        if ivr_matches > human_matches:
            confidence = min(1.0, ivr_matches / max(1, total_matches) + 0.2)
            return IVRMode.IVR, confidence

        if human_matches > ivr_matches:
            confidence = min(1.0, human_matches / max(1, total_matches) + 0.2)
            return IVRMode.CONVERSATION, confidence

        # Tie - default to unknown with low confidence
        return IVRMode.UNKNOWN, 0.3


class LoopDetector:
    """Detects repeating IVR menus using TF-IDF similarity.

    IVR systems often repeat the same menu when no input is received.
    This detector identifies such loops to trigger alternative actions
    like pressing "0" for operator.

    Uses sklearn TfidfVectorizer when available, falls back to Jaccard
    similarity for environments without sklearn.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_history: int = 10,
    ) -> None:
        """Initialize loop detector.

        Args:
            similarity_threshold: Minimum similarity score to consider a loop (0.0-1.0)
            max_history: Maximum transcripts to keep in history
        """
        self.similarity_threshold = similarity_threshold
        self.max_history = max_history
        self._transcripts: list[str] = []
        self._vectorizer: Any | None = None
        self.logger = logger.bind(service="loop_detector")
        self._use_sklearn = self._init_sklearn()

    def _init_sklearn(self) -> bool:
        """Initialize sklearn TfidfVectorizer if available.

        Returns:
            True if sklearn is available, False otherwise
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401

            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),  # Unigrams and bigrams
                stop_words="english",
                max_features=100,
            )
            self.logger.info("loop_detector_using_sklearn")
            return True
        except ImportError:
            self.logger.info("loop_detector_using_fallback_jaccard")
            return False

    def add_transcript(self, transcript: str) -> None:
        """Add a transcript to the history.

        Args:
            transcript: Transcript text to add
        """
        if not transcript or len(transcript.strip()) < 10:
            return

        self._transcripts.append(transcript.lower().strip())

        # Keep history bounded
        if len(self._transcripts) > self.max_history:
            self._transcripts.pop(0)

    def is_loop_detected(self) -> bool:
        """Check if the recent transcripts indicate a loop.

        Returns:
            True if a loop is detected (same IVR menu repeated)
        """
        if len(self._transcripts) < 2:
            return False

        # Compare most recent transcript to previous ones
        recent = self._transcripts[-1]

        for i in range(len(self._transcripts) - 2, -1, -1):
            previous = self._transcripts[i]
            similarity = self._calculate_similarity(recent, previous)

            if similarity >= self.similarity_threshold:
                self.logger.info(
                    "ivr_loop_detected",
                    similarity=similarity,
                    threshold=self.similarity_threshold,
                    recent_preview=recent[:50],
                    previous_preview=previous[:50],
                )
                return True

        return False

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two transcripts.

        Uses TF-IDF cosine similarity if sklearn available,
        otherwise falls back to Jaccard similarity.

        Args:
            text1: First transcript
            text2: Second transcript

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if self._use_sklearn:
            return self._tfidf_similarity(text1, text2)
        return self._jaccard_similarity(text1, text2)

    def _tfidf_similarity(self, text1: str, text2: str) -> float:
        """Calculate TF-IDF cosine similarity.

        Args:
            text1: First transcript
            text2: Second transcript

        Returns:
            Cosine similarity score
        """
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            if self._vectorizer is None:
                return self._jaccard_similarity(text1, text2)

            # Fit and transform both texts
            tfidf_matrix = self._vectorizer.fit_transform([text1, text2])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
            return float(similarity[0][0])
        except Exception as e:
            self.logger.warning("tfidf_similarity_error", error=str(e))
            return self._jaccard_similarity(text1, text2)

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity (fallback method).

        Args:
            text1: First transcript
            text2: Second transcript

        Returns:
            Jaccard similarity score
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def reset(self) -> None:
        """Clear transcript history."""
        self._transcripts.clear()


class DTMFParser:
    """Extract and strip DTMF tags from agent responses.

    The voice agent LLM can include <dtmf>X</dtmf> tags in its response
    to indicate digits that should be sent to navigate IVR menus.

    Example:
        Input: "I'll press 1 for sales <dtmf>1</dtmf>"
        Output: ["1"]
        Stripped: "I'll press 1 for sales"
    """

    def __init__(self, pattern: str = r"<dtmf>([0-9*#A-Dw]+)</dtmf>") -> None:
        """Initialize parser with DTMF tag pattern.

        Args:
            pattern: Regex pattern with capture group for digits.
                     Valid chars: 0-9, *, #, A-D, w (pause)
        """
        self._pattern = re.compile(pattern, re.IGNORECASE)
        self.logger = logger.bind(service="dtmf_parser")

    def parse(self, text: str) -> list[str]:
        """Extract DTMF digits from text.

        Args:
            text: Agent response text

        Returns:
            List of DTMF digit strings found
        """
        if not text:
            return []

        matches = self._pattern.findall(text)

        if matches:
            self.logger.info(
                "dtmf_tags_found",
                digits=matches,
                text_preview=text[:100],
            )

        return matches

    def strip_dtmf_tags(self, text: str) -> str:
        """Remove DTMF tags from text.

        Args:
            text: Agent response text with possible DTMF tags

        Returns:
            Text with DTMF tags removed
        """
        if not text:
            return ""

        return self._pattern.sub("", text).strip()


@dataclass
class IVRDetector:
    """Main orchestrator for IVR detection with callbacks.

    Coordinates the classifier, loop detector, and DTMF parser to
    provide a unified interface for IVR detection and navigation.

    Usage:
        detector = IVRDetector(
            config=IVRDetectorConfig(),
            on_mode_change=handle_mode_change,
            on_loop_detected=handle_loop,
            on_dtmf_detected=handle_dtmf,
        )

        # Process incoming transcripts
        mode = await detector.process_transcript(user_speech, is_agent=False)
        mode = await detector.process_transcript(agent_response, is_agent=True)

    Attributes:
        config: Detection configuration
        on_mode_change: Callback for mode changes (old_mode, new_mode)
        on_loop_detected: Callback when IVR loop detected
        on_dtmf_detected: Callback when DTMF digits found (digits string)
    """

    config: IVRDetectorConfig = field(default_factory=IVRDetectorConfig)
    on_mode_change: Callable[[IVRMode, IVRMode], None] | None = None
    on_loop_detected: Callable[[], None] | None = None
    on_dtmf_detected: Callable[[str], None] | None = None

    def __post_init__(self) -> None:
        """Initialize components after dataclass init."""
        self._classifier = IVRClassifier()
        self._loop_detector = LoopDetector(
            similarity_threshold=self.config.loop_similarity_threshold,
            max_history=self.config.max_transcript_history,
        )
        self._dtmf_parser = DTMFParser(self.config.dtmf_tag_pattern)
        self._status = IVRStatus()
        self.logger = logger.bind(service="ivr_detector")

    @property
    def status(self) -> IVRStatus:
        """Get current IVR detection status."""
        return self._status

    @property
    def mode(self) -> IVRMode:
        """Get current operating mode."""
        return self._status.mode

    async def process_transcript(
        self,
        transcript: str,
        is_agent: bool = False,
    ) -> IVRMode:
        """Process a transcript and update IVR detection state.

        Args:
            transcript: Speech transcript to process
            is_agent: True if this is agent speech, False for user/remote party

        Returns:
            Current IVR mode after processing
        """
        if not transcript or len(transcript.strip()) < self.config.min_transcript_length:
            return self._status.mode

        # For agent transcripts, check for DTMF tags
        if is_agent:
            self._check_dtmf_tags(transcript)
            return self._status.mode

        # For remote party transcripts, classify and detect loops
        mode, confidence = self._classifier.classify(transcript)

        self.logger.info(
            "ivr_transcript_classified",
            mode=mode.value,
            confidence=confidence,
            transcript_preview=transcript[:100],
        )

        # Update consecutive counts based on classification
        self._update_counts(mode)

        # Check if we should switch modes
        self._check_mode_switch()

        # If in IVR mode, check for loops
        if self._status.mode == IVRMode.IVR:
            self._loop_detector.add_transcript(transcript)
            if self._loop_detector.is_loop_detected():
                self._status.loop_detected = True
                if self.on_loop_detected:
                    self.on_loop_detected()

        return self._status.mode

    def _update_counts(self, classified_mode: IVRMode) -> None:
        """Update consecutive classification counts.

        Args:
            classified_mode: Mode from current classification
        """
        if classified_mode in {IVRMode.IVR, IVRMode.VOICEMAIL}:
            self._status.consecutive_ivr_count += 1
            self._status.consecutive_human_count = 0
        elif classified_mode == IVRMode.CONVERSATION:
            self._status.consecutive_human_count += 1
            self._status.consecutive_ivr_count = 0
        # UNKNOWN doesn't reset counts - maintains momentum

    def _check_mode_switch(self) -> None:
        """Check if mode should switch based on consecutive counts."""
        old_mode = self._status.mode
        new_mode = old_mode

        threshold = self.config.consecutive_classifications

        if self._status.consecutive_ivr_count >= threshold:
            new_mode = IVRMode.IVR
        elif self._status.consecutive_human_count >= threshold:
            new_mode = IVRMode.CONVERSATION
            # Reset loop detection when switching to conversation
            self._loop_detector.reset()
            self._status.loop_detected = False

        if new_mode != old_mode:
            self.logger.info(
                "ivr_mode_change",
                old_mode=old_mode.value,
                new_mode=new_mode.value,
                consecutive_ivr=self._status.consecutive_ivr_count,
                consecutive_human=self._status.consecutive_human_count,
            )
            self._status.mode = new_mode
            if self.on_mode_change:
                self.on_mode_change(old_mode, new_mode)

    def _check_dtmf_tags(self, text: str) -> None:
        """Check agent response for DTMF tags.

        Args:
            text: Agent response text
        """
        digits_list = self._dtmf_parser.parse(text)

        for digits in digits_list:
            self._status.last_dtmf_sent = digits
            if self.on_dtmf_detected:
                self.on_dtmf_detected(digits)

    def strip_dtmf_tags(self, text: str) -> str:
        """Strip DTMF tags from text.

        Args:
            text: Text that may contain DTMF tags

        Returns:
            Text with tags removed
        """
        return self._dtmf_parser.strip_dtmf_tags(text)

    def reset(self) -> None:
        """Reset all detection state."""
        self._status = IVRStatus()
        self._loop_detector.reset()
        self.logger.info("ivr_detector_reset")

    def get_ivr_navigation_prompt(self, goal: str | None = None) -> str:
        """Get IVR navigation prompt for the current state.

        Args:
            goal: Optional navigation goal (e.g., "reach sales department")

        Returns:
            Prompt string for IVR navigation
        """
        parts = []

        parts.append(
            "You are navigating an automated phone menu (IVR). "
            "Listen carefully to the options and select the best one."
        )

        if goal:
            parts.append(f"\nYour goal: {goal}")

        if self._status.loop_detected:
            parts.append(
                "\nWARNING: The menu is repeating. Consider pressing '0' "
                "or '#' to reach a human operator, or try a different option."
            )

        parts.append(
            "\nTo select an option, include the digit in <dtmf>X</dtmf> tags. "
            "Example: <dtmf>1</dtmf> to press 1."
        )

        return "\n".join(parts)
