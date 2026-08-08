"""Provider-generic LLM client.

Single branch point for OpenAI vs Anthropic (Claude). Toggle with
LLM_PROVIDER=openai|anthropic in .env — the rest of the app calls
generate_json() / parse_structured() and never imports a provider SDK directly.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from app.config import settings

log = logging.getLogger(__name__)


def llm_configured() -> bool:
    """True when the active provider has an API key set."""
    return bool(settings.llm_api_key)


def _anthropic_effort() -> str:
    """Map the shared reasoning-effort setting onto Anthropic's effort levels."""
    effort = settings.openai_reasoning_effort
    return "low" if effort == "none" else effort


def _anthropic_text(response) -> str:
    """Extract concatenated text blocks from an Anthropic Message."""
    return "".join(block.text for block in response.content if block.type == "text")


def _extract_json_object(text: str) -> str:
    """Slice out the JSON object from a response that may wrap it in prose/fences."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else "{}"


def generate_json(system: str, user_content: str, max_output_tokens: int = 1200) -> dict:
    """Ask the active provider for a JSON object response.

    Raises json.JSONDecodeError if the model returns malformed JSON —
    callers keep their existing fallback behavior.
    """
    if settings.llm_provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=max_output_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": _anthropic_effort()},
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return json.loads(_extract_json_object(_anthropic_text(response)))

    # OpenAI (default)
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.llm_model,
        reasoning={"effort": settings.openai_reasoning_effort},
        max_output_tokens=max_output_tokens,
        text={"format": {"type": "json_object"}},
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return json.loads(getattr(response, "output_text", "") or "{}")


def parse_structured(system: str, user_content: str, schema: type[BaseModel]) -> BaseModel:
    """Ask the active provider for a schema-validated structured response."""
    if settings.llm_provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.parse(
            model=settings.llm_extraction_model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": _anthropic_effort()},
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_format=schema,
        )
        if response.parsed_output is None:
            raise RuntimeError("Anthropic did not return a structured response.")
        return response.parsed_output

    # OpenAI (default)
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key or None)
    response = client.responses.parse(
        model=settings.llm_extraction_model,
        reasoning={"effort": settings.openai_reasoning_effort},
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        text_format=schema,
    )
    if response.output_parsed is None:
        raise RuntimeError("OpenAI did not return a structured response.")
    return response.output_parsed
