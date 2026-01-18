"""AI-powered offer content generation using Hormozi framework.

Generates compelling offer content including headlines, value stacks, guarantees,
urgency elements, and CTAs based on the Hormozi value equation:

Value = (Dream Outcome × Likelihood of Achievement) / (Time × Effort)
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.core.config import settings

logger = structlog.get_logger()

OFFER_GENERATION_SYSTEM_PROMPT = """You are an expert direct-response copywriter \
specializing in the Alex Hormozi value framework. Your goal is to create irresistible \
offers that maximize perceived value using the value equation:

Value = (Dream Outcome × Likelihood of Achievement) / (Time × Effort)

When generating offer content:

1. **Headlines**: Create attention-grabbing headlines that speak to the dream outcome. \
Focus on transformation, not features. Use power words and specificity.

2. **Subheadlines**: Expand on the headline with supporting claims that increase \
believability and desire.

3. **Value Stack Items**: Break down everything included in the offer. For each item:
   - Give it a compelling name
   - Describe the specific benefit (not feature)
   - Assign a perceived value that anchors high

4. **Guarantees**: Create risk-reversing guarantees that remove all buyer hesitation. \
Be bold and specific about what you guarantee.

5. **Urgency/Scarcity**: Create legitimate urgency through limited time, limited \
quantity, or bonus expiration.

6. **CTAs**: Write calls-to-action that are action-oriented and benefit-focused.

Guidelines:
- Focus on outcomes and transformations, not features
- Use specific numbers and timeframes when possible
- Address objections preemptively
- Make the offer feel like a "no-brainer"
- Stack value so high the price seems trivial

Respond ONLY with valid JSON matching the requested structure."""


async def generate_offer_content(
    business_type: str,
    target_audience: str,
    main_offer: str,
    price_point: float | None = None,
    desired_outcome: str | None = None,
    pain_points: list[str] | None = None,
    unique_mechanism: str | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Generate compelling offer content using AI.

    Args:
        business_type: Type of business (e.g., "fitness coaching", "SaaS")
        target_audience: Who the offer is for (e.g., "busy professionals")
        main_offer: The core product/service being offered
        price_point: Optional price point for value anchoring
        desired_outcome: The dream outcome the customer wants
        pain_points: List of customer pain points to address
        unique_mechanism: What makes this offer different
        openai_api_key: Optional API key (uses settings if not provided)

    Returns:
        Generated offer content dict with multiple options per field
    """
    log = logger.bind(
        business_type=business_type,
        target_audience=target_audience,
    )

    api_key = openai_api_key or settings.openai_api_key
    if not api_key:
        log.error("no_openai_api_key")
        return {"success": False, "error": "OpenAI API key not configured"}

    # Build the generation prompt
    prompt_parts = [
        f"Business Type: {business_type}",
        f"Target Audience: {target_audience}",
        f"Main Offer: {main_offer}",
    ]

    if price_point:
        prompt_parts.append(f"Price Point: ${price_point:,.2f}")

    if desired_outcome:
        prompt_parts.append(f"Dream Outcome: {desired_outcome}")

    if pain_points:
        prompt_parts.append(f"Pain Points: {', '.join(pain_points)}")

    if unique_mechanism:
        prompt_parts.append(f"Unique Mechanism: {unique_mechanism}")

    user_prompt = f"""Generate compelling offer content for this business:

{chr(10).join(prompt_parts)}

Generate 3 options for each element. Return JSON with this exact structure:
{{
    "headlines": [
        {{"text": "headline 1", "style": "outcome-focused"}},
        {{"text": "headline 2", "style": "curiosity"}},
        {{"text": "headline 3", "style": "problem-solution"}}
    ],
    "subheadlines": [
        {{"text": "subheadline 1"}},
        {{"text": "subheadline 2"}},
        {{"text": "subheadline 3"}}
    ],
    "value_stack_items": [
        {{
            "name": "item name",
            "description": "benefit description",
            "value": 497
        }},
        ...5-7 items total...
    ],
    "guarantees": [
        {{
            "type": "money_back|satisfaction|results",
            "days": 30,
            "text": "guarantee copy"
        }},
        {{
            "type": "money_back|satisfaction|results",
            "days": 60,
            "text": "guarantee copy"
        }},
        {{
            "type": "money_back|satisfaction|results",
            "days": 90,
            "text": "guarantee copy"
        }}
    ],
    "urgency_options": [
        {{
            "type": "limited_time",
            "text": "urgency message"
        }},
        {{
            "type": "limited_quantity",
            "text": "scarcity message",
            "count": 10
        }},
        {{
            "type": "expiring",
            "text": "bonus expiration message"
        }}
    ],
    "ctas": [
        {{"text": "CTA 1", "subtext": "supporting text"}},
        {{"text": "CTA 2", "subtext": "supporting text"}},
        {{"text": "CTA 3", "subtext": "supporting text"}}
    ],
    "bonus_ideas": [
        {{
            "name": "bonus name",
            "description": "what it is and why it's valuable",
            "value": 197,
            "suggested_type": "pdf|video|checklist|template"
        }},
        ...3 bonus ideas...
    ]
}}"""

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": OFFER_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            log.warning("empty_response")
            return {"success": False, "error": "Empty response from AI"}

        generated: dict[str, Any] = json.loads(content)
        generated["success"] = True

        log.info(
            "offer_content_generated",
            headline_count=len(generated.get("headlines", [])),
            value_stack_count=len(generated.get("value_stack_items", [])),
        )

        return generated

    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        log.exception("generation_error", error=str(e))
        return {"success": False, "error": f"Generation failed: {str(e)}"}
