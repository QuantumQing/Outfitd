"""OpenRouter LLM client — generic caller with structured JSON output."""

import json
import logging
import re
import httpx

from src.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = True,
    model: str | None = None,
) -> dict | str:
    """Call OpenRouter LLM and return parsed JSON or raw text.

    Args:
        system_prompt: System instructions for the LLM.
        user_prompt: User message / task description.
        temperature: Sampling temperature (0-2).
        max_tokens: Maximum response tokens.
        json_mode: If True, request JSON response format.
        model: Optional model override; defaults to settings.openrouter_model.

    Returns:
        Parsed dict if json_mode, raw string otherwise.
    """
    active_model = model or settings.openrouter_model
    logger.debug(f"call_llm using model: {active_model}")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Outfitd Stylist",
    }

    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Only send response_format for models known to support it (DeepSeek).
    # Claude models follow JSON instructions natively without needing this header,
    # and some routes via OpenRouter will reject it.
    if json_mode and "claude" not in active_model.lower():
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    if json_mode:
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
        logger.warning("LLM returned non-JSON despite json_mode; returning raw.")
        return content

    return content


def _extract_json(content: str) -> dict | None:
    """Try multiple strategies to extract a JSON object from LLM output."""
    # 1. Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences (```json ... ```)
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped.strip())
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Find first { ... last } in the response (handles prose + JSON mixed output)
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None
