"""AI-powered review reply drafting for the reputation engine.

Generates a short, on-brand reply to a customer review. Public 5-star reviews get
a warm thank-you; negative private feedback gets an empathetic, de-escalating
response that offers to make things right. Mirrors the generation pattern in
:mod:`app.services.ai.offer_generator` (graceful failure dict, shared OpenAI
credential resolution, JSON-mode response).
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.services.ai.openai_credentials import get_openai_bearer_token

logger = structlog.get_logger()

REVIEW_REPLY_SYSTEM_PROMPT = """You are a customer-experience manager writing \
public-facing replies to customer reviews for a local service business. Your \
replies must be:

- Short (1-3 sentences, under 60 words). This is a public reply, not an essay.
- Warm, human, and specific — reference the customer's point, never generic.
- On-brand and professional; never defensive, never argumentative.
- Free of personal data, discounts you can't honor, or legal admissions.

For POSITIVE reviews: thank the customer sincerely and invite them back.

For NEGATIVE reviews/feedback: open with genuine empathy, apologize for the \
experience without making excuses, and offer a concrete next step to make it \
right (e.g. a direct contact). Aim to de-escalate and move the conversation \
offline.

Respond ONLY with valid JSON: {"reply": "..."}."""


async def generate_review_reply(
    *,
    rating: int,
    review_body: str | None,
    is_public: bool,
    business_name: str | None = None,
    reviewer_name: str | None = None,
    tone: str | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Generate an on-brand reply draft for a review.

    Args:
        rating: Star rating 1-5.
        review_body: The customer's review/feedback text, if any.
        is_public: Whether this is a public review (vs private negative feedback).
        business_name: Business name to sign off as.
        reviewer_name: Reviewer's first name, for personalization.
        tone: Optional brand-voice guidance.
        openai_api_key: Optional override; falls back to shared credentials.

    Returns:
        Dict with ``success`` plus ``reply`` on success or ``error`` on failure.
    """
    log = logger.bind(rating=rating, is_public=is_public)

    api_key = openai_api_key or get_openai_bearer_token()
    if not api_key:
        log.error("no_openai_api_key")
        return {"success": False, "error": "OpenAI API key not configured"}

    sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"

    prompt_parts = [
        f"Star rating: {rating} out of 5 ({sentiment}).",
        f"Review type: {'public review' if is_public else 'private feedback'}.",
    ]
    if business_name:
        prompt_parts.append(f"Business name: {business_name}")
    if reviewer_name:
        prompt_parts.append(f"Reviewer first name: {reviewer_name}")
    if review_body:
        prompt_parts.append(f"What the customer wrote: {review_body}")
    else:
        prompt_parts.append("The customer left a star rating with no written comment.")
    if tone:
        prompt_parts.append(f"Brand voice / tone guidance: {tone}")

    user_prompt = (
        "Write a single reply to this review.\n\n"
        + "\n".join(prompt_parts)
        + '\n\nReturn JSON: {"reply": "your reply text"}'
    )

    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": REVIEW_REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_completion_tokens=400,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            log.warning("empty_response")
            return {"success": False, "error": "Empty response from AI"}

        parsed: dict[str, Any] = json.loads(content)
        reply = parsed.get("reply")
        if not reply or not isinstance(reply, str):
            log.warning("missing_reply_field")
            return {"success": False, "error": "AI response missing reply text"}

        log.info("review_reply_generated", reply_length=len(reply))
        return {"success": True, "reply": reply.strip()}

    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        log.exception("generation_error", error=str(e))
        return {"success": False, "error": f"Generation failed: {str(e)}"}
