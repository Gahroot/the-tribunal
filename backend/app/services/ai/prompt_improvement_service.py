"""LLM-powered prompt optimization service.

Analyzes call performance and generates improved prompt variations
using AI to identify patterns in successful vs unsuccessful calls.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.call_outcome import CallOutcome, OutcomeType
from app.models.improvement_suggestion import ImprovementSuggestion
from app.models.prompt_version import PromptVersion
from app.services.ai.prompt_version_service import PromptVersionService

logger = structlog.get_logger()

# Mutation types with descriptions
MUTATION_TYPES = {
    "warmer_tone": "Make the prompt warmer and more personable",
    "more_concise": "Make the prompt more direct and concise",
    "add_urgency": "Add subtle urgency to encourage action",
    "better_objections": "Improve objection handling responses",
    "more_personalization": "Add more personalization techniques",
    "clearer_value": "Clarify the value proposition",
    "natural_flow": "Make the conversation flow more naturally",
    "trust_building": "Add more trust-building elements",
}


@dataclass
class PromptAnalysis:
    """Analysis of prompt performance."""

    strengths: list[str]
    weaknesses: list[str]
    improvement_areas: list[str]
    recommended_mutations: list[str]
    summary: str


@dataclass
class GeneratedVariation:
    """A generated prompt variation."""

    prompt: str
    greeting: str | None
    mutation_type: str
    expected_improvement: str


class PromptImprovementService:
    """LLM-powered prompt optimization.

    Analyzes call outcomes to identify patterns and generate
    improved prompt variations for A/B testing.
    """

    def __init__(self) -> None:
        """Initialize the service."""
        self._client: AsyncOpenAI | None = None
        self._prompt_service = PromptVersionService()

    def _get_client(self) -> AsyncOpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def analyze_performance(
        self,
        db: AsyncSession,
        version: PromptVersion,
        limit: int = 50,
    ) -> PromptAnalysis:
        """Analyze why a prompt version performs well or poorly.

        Examines successful vs unsuccessful call patterns to identify
        strengths and areas for improvement.

        Args:
            db: Database session
            version: Prompt version to analyze
            limit: Max outcomes to analyze

        Returns:
            PromptAnalysis with insights
        """
        log = logger.bind(version_id=str(version.id))

        # Get recent outcomes for this version
        successful_query = (
            select(CallOutcome)
            .where(
                CallOutcome.prompt_version_id == version.id,
                CallOutcome.outcome_type.in_([
                    OutcomeType.APPOINTMENT_BOOKED.value,
                    OutcomeType.LEAD_QUALIFIED.value,
                ]),
            )
            .order_by(CallOutcome.created_at.desc())
            .limit(limit // 2)
        )

        failed_query = (
            select(CallOutcome)
            .where(
                CallOutcome.prompt_version_id == version.id,
                CallOutcome.outcome_type.in_([
                    OutcomeType.REJECTED.value,
                    OutcomeType.FAILED.value,
                ]),
            )
            .order_by(CallOutcome.created_at.desc())
            .limit(limit // 2)
        )

        successful_result = await db.execute(successful_query)
        failed_result = await db.execute(failed_query)

        successful_outcomes = list(successful_result.scalars().all())
        failed_outcomes = list(failed_result.scalars().all())

        log.debug(
            "Analyzing outcomes",
            successful_count=len(successful_outcomes),
            failed_count=len(failed_outcomes),
        )

        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(
            version, successful_outcomes, failed_outcomes
        )

        # Call LLM for analysis
        client = self._get_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at analyzing AI voice agent prompts for sales "
                        "and appointment booking. Analyze the provided prompt and call outcomes "
                        "to identify patterns in successful vs unsuccessful calls."
                    ),
                },
                {"role": "user", "content": analysis_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        # Parse response
        import json

        analysis_text = response.choices[0].message.content or "{}"
        analysis_data = json.loads(analysis_text)

        return PromptAnalysis(
            strengths=analysis_data.get("strengths", []),
            weaknesses=analysis_data.get("weaknesses", []),
            improvement_areas=analysis_data.get("improvement_areas", []),
            recommended_mutations=analysis_data.get("recommended_mutations", []),
            summary=analysis_data.get("summary", "No analysis available"),
        )

    async def generate_variations(
        self,
        version: PromptVersion,
        analysis: PromptAnalysis,
        num_variations: int = 3,
    ) -> list[GeneratedVariation]:
        """Generate improved prompt variations based on analysis.

        Args:
            version: Source prompt version
            analysis: Performance analysis
            num_variations: Number of variations to generate

        Returns:
            List of generated variations
        """
        variations: list[GeneratedVariation] = []

        # Use recommended mutations or default set
        mutations = analysis.recommended_mutations[:num_variations]
        if len(mutations) < num_variations:
            # Fill with common improvements
            defaults = ["more_concise", "warmer_tone", "better_objections"]
            for m in defaults:
                if m not in mutations and len(mutations) < num_variations:
                    mutations.append(m)

        for mutation_type in mutations:
            variation = await self._generate_single_variation(
                version, analysis, mutation_type
            )
            if variation:
                variations.append(variation)

        return variations

    async def _generate_single_variation(
        self,
        version: PromptVersion,
        analysis: PromptAnalysis,
        mutation_type: str,
    ) -> GeneratedVariation | None:
        """Generate a single prompt variation.

        Args:
            version: Source prompt version
            analysis: Performance analysis
            mutation_type: Type of mutation to apply

        Returns:
            Generated variation or None on failure
        """
        mutation_desc = MUTATION_TYPES.get(mutation_type, "Improve the prompt")

        generation_prompt = f"""Based on this analysis of the current prompt's performance:

ANALYSIS SUMMARY:
{analysis.summary}

WEAKNESSES IDENTIFIED:
{chr(10).join(f'- {w}' for w in analysis.weaknesses)}

IMPROVEMENT AREAS:
{chr(10).join(f'- {a}' for a in analysis.improvement_areas)}

CURRENT PROMPT:
{version.system_prompt}

CURRENT GREETING:
{version.initial_greeting or 'None'}

YOUR TASK: {mutation_desc}

Generate an improved version of the prompt that addresses the weaknesses while maintaining
the core functionality. Make specific, targeted changes rather than rewriting everything.

Return JSON with:
- "improved_prompt": The improved system prompt
- "improved_greeting": The improved greeting (or null if unchanged)
- "changes_made": Brief description of specific changes
- "expected_improvement": What improvement this should bring
"""

        client = self._get_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at optimizing AI voice agent prompts for sales. "
                        "Make targeted improvements while preserving the prompt's core purpose."
                    ),
                },
                {"role": "user", "content": generation_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        import json

        result_text = response.choices[0].message.content or "{}"
        result = json.loads(result_text)

        if not result.get("improved_prompt"):
            return None

        return GeneratedVariation(
            prompt=result["improved_prompt"],
            greeting=result.get("improved_greeting"),
            mutation_type=mutation_type,
            expected_improvement=result.get("expected_improvement", ""),
        )

    async def create_suggestion(
        self,
        db: AsyncSession,
        version: PromptVersion,
        variation: GeneratedVariation,
        analysis_summary: str,
    ) -> ImprovementSuggestion:
        """Create a suggestion in the queue.

        Args:
            db: Database session
            version: Source version
            variation: Generated variation
            analysis_summary: Summary of the analysis

        Returns:
            Created suggestion
        """
        suggestion = ImprovementSuggestion(
            agent_id=version.agent_id,
            source_version_id=version.id,
            suggested_prompt=variation.prompt,
            suggested_greeting=variation.greeting,
            mutation_type=variation.mutation_type,
            analysis_summary=analysis_summary,
            expected_improvement=variation.expected_improvement,
            status="pending",
        )

        db.add(suggestion)
        await db.flush()
        await db.refresh(suggestion)

        return suggestion

    async def approve_suggestion(
        self,
        db: AsyncSession,
        suggestion_id: uuid.UUID,
        user_id: int | None = None,
        activate: bool = True,
    ) -> tuple[ImprovementSuggestion, PromptVersion]:
        """Approve a suggestion and create a new prompt version.

        Args:
            db: Database session
            suggestion_id: Suggestion to approve
            user_id: User approving
            activate: Whether to activate for testing

        Returns:
            Tuple of (updated suggestion, created version)
        """
        result = await db.execute(
            select(ImprovementSuggestion).where(ImprovementSuggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()

        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")

        if suggestion.status != "pending":
            raise ValueError(f"Suggestion is {suggestion.status}, not pending")

        # Create new prompt version
        new_version = await self._prompt_service.create_version(
            db=db,
            agent_id=suggestion.agent_id,
            system_prompt=suggestion.suggested_prompt,
            initial_greeting=suggestion.suggested_greeting,
            change_summary=f"AI improvement: {suggestion.mutation_type}",
            created_by_id=user_id,
            activate=False,
            parent_version_id=suggestion.source_version_id,
        )

        # Update suggestion
        suggestion.status = "approved"
        suggestion.reviewed_at = datetime.now(UTC)
        suggestion.reviewed_by_id = user_id
        suggestion.created_version_id = new_version.id

        # Optionally activate for testing
        if activate:
            await self._prompt_service.activate_for_testing(db, new_version.id)

        await db.commit()
        await db.refresh(suggestion)
        await db.refresh(new_version)

        return suggestion, new_version

    async def reject_suggestion(
        self,
        db: AsyncSession,
        suggestion_id: uuid.UUID,
        user_id: int | None = None,
        reason: str | None = None,
    ) -> ImprovementSuggestion:
        """Reject a suggestion.

        Args:
            db: Database session
            suggestion_id: Suggestion to reject
            user_id: User rejecting
            reason: Optional rejection reason

        Returns:
            Updated suggestion
        """
        result = await db.execute(
            select(ImprovementSuggestion).where(ImprovementSuggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()

        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")

        if suggestion.status != "pending":
            raise ValueError(f"Suggestion is {suggestion.status}, not pending")

        suggestion.status = "rejected"
        suggestion.reviewed_at = datetime.now(UTC)
        suggestion.reviewed_by_id = user_id
        suggestion.rejection_reason = reason

        await db.commit()
        await db.refresh(suggestion)

        return suggestion

    def _calc_rate(self, numerator: int, denominator: int) -> float:
        """Calculate rate as percentage, return 0 if denominator is 0."""
        return (numerator / denominator * 100) if denominator > 0 else 0

    def _build_analysis_prompt(
        self,
        version: PromptVersion,
        successful: list[CallOutcome],
        failed: list[CallOutcome],
    ) -> str:
        """Build the analysis prompt for the LLM."""
        # Extract signals from outcomes for context
        successful_signals = [
            {
                "outcome": o.outcome_type,
                "signals": o.signals,
            }
            for o in successful[:10]
        ]

        failed_signals = [
            {
                "outcome": o.outcome_type,
                "signals": o.signals,
            }
            for o in failed[:10]
        ]

        return f"""Analyze this AI voice agent prompt's performance.

PROMPT BEING ANALYZED:
{version.system_prompt}

INITIAL GREETING:
{version.initial_greeting or 'None'}

STATISTICS:
- Total calls: {version.total_calls}
- Successful calls: {version.successful_calls}
- Appointments booked: {version.booked_appointments}
- Success rate: {self._calc_rate(version.successful_calls, version.total_calls):.1f}%
- Booking rate: {self._calc_rate(version.booked_appointments, version.successful_calls):.1f}%

SAMPLE SUCCESSFUL OUTCOMES:
{successful_signals}

SAMPLE FAILED OUTCOMES:
{failed_signals}

Analyze patterns and return JSON with:
- "strengths": List of what the prompt does well
- "weaknesses": List of areas where the prompt falls short
- "improvement_areas": Specific actionable improvements
- "recommended_mutations": List from [{', '.join(MUTATION_TYPES.keys())}]
- "summary": 2-3 sentence summary of the analysis
"""
