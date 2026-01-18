"""AI-powered lead magnet content generation.

Generates quiz questions, calculator configurations, and rich content
for interactive lead magnets.
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.core.config import settings

logger = structlog.get_logger()

QUIZ_GENERATION_SYSTEM_PROMPT = """You are an expert at creating engaging qualification quizzes \
that help segment and qualify leads while providing value to the quiz taker.

When generating quiz content:

1. **Questions**: Create questions that:
   - Are engaging and relevant to the topic
   - Help qualify the lead (budget, timeline, needs, authority)
   - Can be answered quickly (under 10 seconds per question)
   - Mix question types for variety

2. **Scoring**: Design scoring that:
   - Creates meaningful segments (e.g., "Ready to Buy", "Needs Nurturing", "Not a Fit")
   - Provides value to the quiz taker through their results
   - Helps the business prioritize leads

3. **Results**: Create result messages that:
   - Provide genuine value and insights
   - Create a next step or call to action
   - Make the lead feel understood

Respond ONLY with valid JSON matching the requested structure."""


CALCULATOR_GENERATION_SYSTEM_PROMPT = """You are an expert at creating ROI and value calculators \
that help prospects understand the value of a product or service.

When generating calculator content:

1. **Input Fields**: Design inputs that:
   - Are easy to estimate or know
   - Directly impact the calculated value
   - Create personalized results

2. **Formulas**: Create calculations that:
   - Are logical and defensible
   - Show real ROI or savings
   - Can be explained simply

3. **Output Formatting**: Present results that:
   - Highlight the key value metrics
   - Compare current state vs. improved state
   - Create urgency to take action

Respond ONLY with valid JSON matching the requested structure."""


async def generate_quiz_content(
    topic: str,
    target_audience: str,
    goal: str,
    num_questions: int = 5,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Generate quiz questions and scoring configuration.

    Args:
        topic: What the quiz is about (e.g., "marketing readiness")
        target_audience: Who will take the quiz
        goal: What to qualify for (e.g., "marketing agency services")
        num_questions: Number of questions to generate (5-7 recommended)
        openai_api_key: Optional API key (uses settings if not provided)

    Returns:
        Generated quiz content with questions, options, scoring, and results
    """
    log = logger.bind(topic=topic, num_questions=num_questions)

    api_key = openai_api_key or settings.openai_api_key
    if not api_key:
        log.error("no_openai_api_key")
        return {"success": False, "error": "OpenAI API key not configured"}

    user_prompt = f"""Generate a qualification quiz for:

Topic: {topic}
Target Audience: {target_audience}
Goal: {goal}
Number of Questions: {num_questions}

Return JSON with this exact structure:
{{
    "title": "Quiz title",
    "description": "Brief quiz description",
    "questions": [
        {{
            "id": "q1",
            "text": "Question text",
            "type": "single_choice",
            "options": [
                {{
                    "id": "q1_a",
                    "text": "Option text",
                    "score": 10
                }},
                {{
                    "id": "q1_b",
                    "text": "Option text",
                    "score": 5
                }},
                {{
                    "id": "q1_c",
                    "text": "Option text",
                    "score": 0
                }}
            ]
        }}
    ],
    "results": [
        {{
            "id": "high",
            "min_score": 40,
            "max_score": 100,
            "title": "Result title for high scorers",
            "description": "What this means and next steps",
            "cta_text": "Call to action button text"
        }},
        {{
            "id": "medium",
            "min_score": 20,
            "max_score": 39,
            "title": "Result title for medium scorers",
            "description": "What this means and next steps",
            "cta_text": "Call to action button text"
        }},
        {{
            "id": "low",
            "min_score": 0,
            "max_score": 19,
            "title": "Result title for low scorers",
            "description": "What this means and next steps",
            "cta_text": "Call to action button text"
        }}
    ]
}}

Question types can be: single_choice, multiple_choice, scale (1-10)
For scale type, score = selected value * weight (include "weight" field)"""

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": QUIZ_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
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
            "quiz_content_generated",
            question_count=len(generated.get("questions", [])),
            result_count=len(generated.get("results", [])),
        )

        return generated

    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        log.exception("generation_error", error=str(e))
        return {"success": False, "error": f"Generation failed: {str(e)}"}


async def generate_calculator_content(
    calculator_type: str,
    industry: str,
    target_audience: str,
    value_proposition: str,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Generate calculator fields and formula configuration.

    Args:
        calculator_type: Type of calculator (e.g., "ROI", "savings", "cost")
        industry: Industry context
        target_audience: Who will use the calculator
        value_proposition: What value you're trying to demonstrate
        openai_api_key: Optional API key (uses settings if not provided)

    Returns:
        Generated calculator content with fields, formulas, and output config
    """
    log = logger.bind(calculator_type=calculator_type, industry=industry)

    api_key = openai_api_key or settings.openai_api_key
    if not api_key:
        log.error("no_openai_api_key")
        return {"success": False, "error": "OpenAI API key not configured"}

    user_prompt = f"""Generate a {calculator_type} calculator for:

Industry: {industry}
Target Audience: {target_audience}
Value Proposition: {value_proposition}

Return JSON with this exact structure:
{{
    "title": "Calculator title",
    "description": "Brief description of what this calculates",
    "inputs": [
        {{
            "id": "input1",
            "label": "Field label",
            "type": "number",
            "placeholder": "e.g., 10000",
            "default_value": 0,
            "prefix": "$",
            "suffix": "",
            "help_text": "Explanation of what to enter",
            "required": true
        }},
        {{
            "id": "input2",
            "label": "Field label",
            "type": "percentage",
            "placeholder": "e.g., 20",
            "default_value": 0,
            "suffix": "%",
            "help_text": "Explanation",
            "required": true
        }},
        {{
            "id": "input3",
            "label": "Dropdown field",
            "type": "select",
            "options": [
                {{"value": "option1", "label": "Option 1", "multiplier": 1.0}},
                {{"value": "option2", "label": "Option 2", "multiplier": 1.5}}
            ],
            "required": true
        }}
    ],
    "calculations": [
        {{
            "id": "calc1",
            "label": "Intermediate calculation label",
            "formula": "input1 * (input2 / 100)",
            "format": "currency"
        }}
    ],
    "outputs": [
        {{
            "id": "primary_result",
            "label": "Main result label",
            "formula": "calc1 * 12",
            "format": "currency",
            "highlight": true,
            "description": "What this number means"
        }},
        {{
            "id": "secondary_result",
            "label": "Secondary metric",
            "formula": "calc1 / input1 * 100",
            "format": "percentage",
            "highlight": false,
            "description": "What this percentage represents"
        }}
    ],
    "cta": {{
        "text": "Call to action button",
        "description": "Why they should take this action"
    }}
}}

Input types: number, currency, percentage, select
Output formats: currency, percentage, number, text"""

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CALCULATOR_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            log.warning("empty_response")
            return {"success": False, "error": "Empty response from AI"}

        generated: dict[str, Any] = json.loads(content)
        generated["success"] = True

        log.info(
            "calculator_content_generated",
            input_count=len(generated.get("inputs", [])),
            output_count=len(generated.get("outputs", [])),
        )

        return generated

    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        log.exception("generation_error", error=str(e))
        return {"success": False, "error": f"Generation failed: {str(e)}"}
