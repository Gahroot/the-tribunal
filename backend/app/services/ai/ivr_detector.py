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


class DTMFContext(Enum):
    """Context for DTMF input expectations."""

    UNKNOWN = "unknown"
    MENU = "menu"  # Single digit (1-9, 0, *, #)
    EXTENSION = "extension"  # Multi-digit with # terminator
    PIN = "pin"  # Multi-digit PIN
    VOICEMAIL = "voicemail"  # Don't press buttons


@dataclass
class IVRMenuState:
    """State of current IVR menu."""

    context: DTMFContext = DTMFContext.UNKNOWN
    attempted_dtmf: set[str] = field(default_factory=set)
    failed_dtmf: set[str] = field(default_factory=set)
    last_menu_text: str | None = None


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
        attempted_dtmf: Set of all DTMF digits that have been tried
        failed_dtmf: Set of DTMF digits that didn't change the menu
        last_menu_transcript: Last menu transcript for change detection
        menu_state: Current IVR menu state
    """

    mode: IVRMode = IVRMode.UNKNOWN
    loop_detected: bool = False
    consecutive_ivr_count: int = 0
    consecutive_human_count: int = 0
    last_dtmf_sent: str | None = None
    attempted_dtmf: set[str] = field(default_factory=set)
    failed_dtmf: set[str] = field(default_factory=set)
    last_menu_transcript: str | None = None
    menu_state: IVRMenuState = field(default_factory=IVRMenuState)


class IVRClassifier:
    """Rule-based classifier for IVR, human, and voicemail detection.

    Uses regex patterns to quickly classify transcripts without API latency.
    Patterns are based on common IVR menu phrases and human speech indicators.

    IMPORTANT: When exclusive IVR patterns (DTMF prompts) are detected, the
    classifier will ALWAYS return IVR, even if voicemail patterns also match.
    This prevents misclassification of "Press 1 to leave a message" as voicemail.
    """

    # EXCLUSIVE IVR patterns - DTMF prompts that indicate a navigable menu
    # If ANY of these match, the transcript is ALWAYS IVR, never voicemail
    # These are patterns where user input is expected/requested
    EXCLUSIVE_IVR_PATTERNS: list[str] = [
        r"press\s+[0-9*#]",  # "Press 1", "Press 2", "Press star"
        r"dial\s+[0-9*#]",  # "Dial 0 for operator"
        r"for\s+\w+\s*,?\s*press",  # "For sales, press 1"
        r"to\s+\w+\s*,?\s*press",  # "To speak to a representative, press 0"
        r"option\s+[0-9]",  # "Option 1 is for billing"
        r"say\s+or\s+press",  # "Say or press 1"
        r"enter\s+your\s+(account|pin|phone|extension)",  # "Enter your account number"
    ]

    # IVR error/retry patterns - indicate IVR detected invalid input
    # These messages mean we're still in IVR mode and need to retry
    # NOTE: Patterns must be specific to avoid false positives with voicemail
    IVR_ERROR_PATTERNS: list[str] = [
        r"is\s+not\s+a\s+valid\s+extension",  # "That is not a valid extension"
        r"invalid\s+(selection|option|entry|input)",  # "Invalid selection"
        r"please\s+try\s+again\b(?!\s+later)",  # "Please try again" but NOT "try again later"
        r"that\s+is\s+not\s+(a\s+valid\s+)?an?\s+option",  # "That is not an option"
        r"did\s+not\s+(recognize|understand)",  # "I did not recognize your input"
        r"not\s+a\s+valid\s+(option|selection|choice|entry)",  # "Not a valid option"
        r"incorrect\s+(entry|selection|choice|input)",  # "Incorrect entry"
        r"unrecognized\s+(input|selection)",  # "Unrecognized input"
    ]

    # IVR menu patterns - phrases that indicate automated phone systems
    # (Does NOT include "leave a message" or "at the beep" which are voicemail-only)
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

    # Voicemail patterns - ONLY match when NO exclusive IVR patterns present
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
    ]

    def __init__(self) -> None:
        """Initialize classifier with compiled regex patterns."""
        self._exclusive_ivr_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.EXCLUSIVE_IVR_PATTERNS
        ]
        self._ivr_error_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.IVR_ERROR_PATTERNS
        ]
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

        Priority order:
        1. If ANY exclusive IVR pattern matches (DTMF prompts) → IVR (always)
        2. If human patterns dominate → CONVERSATION
        3. If voicemail patterns match AND no IVR patterns → VOICEMAIL
        4. If IVR patterns match → IVR
        5. Otherwise → UNKNOWN

        Args:
            transcript: Speech transcript to classify

        Returns:
            Tuple of (classification mode, confidence score 0.0-1.0)
        """
        if not transcript or len(transcript.strip()) < 5:
            return IVRMode.UNKNOWN, 0.0

        text = transcript.lower().strip()
        counts = self._count_pattern_matches(text)

        self.logger.debug("ivr_classification", transcript_preview=text[:100], **counts)

        return self._determine_mode(counts)

    def _count_pattern_matches(self, text: str) -> dict[str, int]:
        """Count pattern matches for each category."""
        exclusive = sum(1 for p in self._exclusive_ivr_patterns if p.search(text))
        ivr_error = sum(1 for p in self._ivr_error_patterns if p.search(text))
        ivr = sum(1 for p in self._ivr_patterns if p.search(text))
        human = sum(1 for p in self._human_patterns if p.search(text))
        voicemail = sum(1 for p in self._voicemail_patterns if p.search(text))

        return {
            "exclusive_ivr_matches": exclusive,
            "ivr_error_matches": ivr_error,
            "ivr_matches": ivr,
            "human_matches": human,
            "voicemail_matches": voicemail,
            "total_matches": ivr + ivr_error + human + voicemail,
        }

    def _determine_mode(self, counts: dict[str, int]) -> tuple[IVRMode, float]:
        """Determine mode based on pattern match counts."""
        exclusive = counts["exclusive_ivr_matches"]
        ivr_error = counts["ivr_error_matches"]
        ivr = counts["ivr_matches"]
        human = counts["human_matches"]
        voicemail = counts["voicemail_matches"]
        total = counts["total_matches"]

        # PRIORITY 1: Exclusive IVR patterns ALWAYS win (DTMF prompts)
        # PRIORITY 2: IVR error patterns (invalid input messages)
        # Both indicate we're in IVR mode
        if exclusive > 0 or ivr_error > 0:
            ratio = (exclusive + ivr + ivr_error) / max(1, total)
            # Slightly lower confidence boost for error-only matches
            boost = 0.3 if exclusive > 0 else 0.25
            return IVRMode.IVR, min(1.0, ratio + boost)

        # No patterns matched
        if total == 0:
            return IVRMode.UNKNOWN, 0.0

        # PRIORITY 3: Human patterns dominate
        if human > ivr and human > voicemail:
            return IVRMode.CONVERSATION, min(1.0, human / total + 0.2)

        # PRIORITY 4: Voicemail ONLY if no IVR patterns
        if voicemail > 0 and ivr == 0:
            return IVRMode.VOICEMAIL, min(1.0, voicemail / total + 0.2)

        # PRIORITY 5: IVR patterns present (or tie/unclear → unknown)
        if ivr > 0:
            return IVRMode.IVR, min(1.0, ivr / total + 0.2)

        return IVRMode.UNKNOWN, 0.3

    def detect_context(self, transcript: str) -> DTMFContext:
        """Detect what type of DTMF input is expected.

        Args:
            transcript: The IVR menu transcript

        Returns:
            DTMFContext indicating expected input type
        """
        text = transcript.lower()

        if re.search(r"enter.*extension|dial.*extension", text):
            return DTMFContext.EXTENSION
        if re.search(r"enter.*pin|enter.*password", text):
            return DTMFContext.PIN
        if re.search(r"leave.*message|after.*beep", text):
            return DTMFContext.VOICEMAIL
        if re.search(r"press\s+[0-9]|option\s+[0-9]", text):
            return DTMFContext.MENU

        return DTMFContext.UNKNOWN


class DTMFValidator:
    """Validate and split DTMF based on context."""

    def split_dtmf_by_context(self, digits: str, context: DTMFContext) -> list[str]:
        """Split multi-digit string based on IVR context.

        Examples:
            ("220", MENU) -> ["2", "2", "0"]  # Individual presses
            ("220", EXTENSION) -> ["220#"]     # Together with terminator

        Args:
            digits: The DTMF digits to split
            context: The IVR context indicating expected input type

        Returns:
            List of DTMF sequences to send
        """
        if context == DTMFContext.MENU:
            return list(digits)  # Split into individual
        elif context == DTMFContext.EXTENSION:
            return [f"{digits}#"] if not digits.endswith("#") else [digits]
        elif context in {DTMFContext.PIN}:
            return [digits]  # Together, no terminator
        else:
            # Unknown: default to individual (safe)
            return list(digits)


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

        # For agent transcripts, check DTMF AND add to loop detection
        if is_agent:
            self._check_dtmf_tags(transcript)

            # Track agent DTMF for loop detection
            if self._status.mode == IVRMode.IVR and self._status.last_dtmf_sent:
                synthetic = f"Pressed {self._status.last_dtmf_sent}"
                self._loop_detector.add_transcript(synthetic)

                if self._loop_detector.is_loop_detected():
                    self._status.loop_detected = True
                    self.logger.warning("agent_dtmf_loop_detected")

            return self._status.mode

        # For remote party transcripts, classify and detect loops
        mode, confidence = self._classifier.classify(transcript)

        # Detect context from transcript
        detected_context = self._classifier.detect_context(transcript)
        if detected_context != DTMFContext.UNKNOWN:
            self._status.menu_state.context = detected_context
            self.logger.info("ivr_context_detected", context=detected_context.value)

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
        """Check agent response for DTMF tags and track digits.

        NOTE: This method only TRACKS DTMF digits for loop detection purposes.
        It does NOT send DTMF. The DTMFHandler.check_and_send() is the single
        source of truth for sending DTMF to prevent duplication bugs.

        Args:
            text: Agent response text
        """
        digits_list = self._dtmf_parser.parse(text)

        for digits in digits_list:
            # Track the digit for loop detection - but do NOT invoke callback
            # The DTMFHandler is responsible for actually sending DTMF
            self._status.last_dtmf_sent = digits

    def strip_dtmf_tags(self, text: str) -> str:
        """Strip DTMF tags from text.

        Args:
            text: Text that may contain DTMF tags

        Returns:
            Text with tags removed
        """
        return self._dtmf_parser.strip_dtmf_tags(text)

    def record_dtmf_attempt(self, digits: str) -> None:
        """Record a DTMF attempt.

        Args:
            digits: The DTMF digits that were sent
        """
        self._status.attempted_dtmf.add(digits)
        self._status.last_dtmf_sent = digits
        # Also record in menu_state
        if self._status.menu_state:
            self._status.menu_state.attempted_dtmf.add(digits)
        self.logger.debug(
            "dtmf_attempt_recorded",
            digits=digits,
            total_attempted=len(self._status.attempted_dtmf),
        )

    def record_dtmf_failed(self, digits: str) -> None:
        """Record that a DTMF didn't change the menu.

        Args:
            digits: The DTMF digits that failed to produce a change
        """
        self._status.failed_dtmf.add(digits)
        self.logger.info(
            "dtmf_marked_as_failed",
            digits=digits,
            total_failed=len(self._status.failed_dtmf),
        )

    def get_untried_digits(self) -> list[str]:
        """Get menu digits (1-9) not yet attempted.

        Returns:
            Sorted list of digits that haven't been tried yet
        """
        all_digits = set("123456789")
        return sorted(all_digits - self._status.attempted_dtmf)

    def should_skip_digit(self, digits: str) -> bool:
        """Check if digit already failed.

        Args:
            digits: The DTMF digits to check

        Returns:
            True if the digits have already been tried and failed
        """
        return digits in self._status.failed_dtmf

    def validate_menu_changed(self, new_transcript: str) -> bool:
        """Check if menu changed after DTMF.

        Compares the new transcript with the last menu transcript to determine
        if the DTMF press actually navigated to a different menu.

        Args:
            new_transcript: The new transcript from the IVR

        Returns:
            True if menu is different (DTMF worked), False if same (DTMF failed)
        """
        if not self._status.last_menu_transcript:
            self._status.last_menu_transcript = new_transcript
            return True

        similarity = self._loop_detector._calculate_similarity(
            self._status.last_menu_transcript,
            new_transcript,
        )

        menu_changed = similarity < self.config.loop_similarity_threshold

        # If menu didn't change and we sent DTMF, mark it as failed
        if not menu_changed and self._status.last_dtmf_sent:
            self.record_dtmf_failed(self._status.last_dtmf_sent)
            self.logger.warning(
                "dtmf_did_not_change_menu",
                digits=self._status.last_dtmf_sent,
                similarity=similarity,
                threshold=self.config.loop_similarity_threshold,
            )

        # Update last menu transcript
        self._status.last_menu_transcript = new_transcript
        return menu_changed

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

        # Add info about tried digits
        if self._status.attempted_dtmf:
            tried = ", ".join(sorted(self._status.attempted_dtmf))
            parts.append(f"\nDigits already tried: {tried}")

        if self._status.failed_dtmf:
            failed = ", ".join(sorted(self._status.failed_dtmf))
            parts.append(f"Digits that didn't work: {failed}")

        untried = self.get_untried_digits()
        if untried and self._status.attempted_dtmf:
            parts.append(f"Try one of these next: {', '.join(untried[:3])}")

        if self._status.loop_detected:
            parts.append(
                "\nWARNING: The menu is repeating. Try a DIFFERENT numbered option (1-9) "
                "that you haven't tried yet. Only use '0' or '#' as a last resort."
            )

        parts.append(
            "\nTo select an option, include the digit in <dtmf>X</dtmf> tags. "
            "Example: <dtmf>1</dtmf> to press 1."
        )

        return "\n".join(parts)
