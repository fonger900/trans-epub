"""Google Gemini translation engine."""

import json
import os

from .base import (
    ENGINES,
    LLM_PROMPT,
    EngineConfig,
    call_with_retry,
    extract_translations,
    http_session,
)


def gemini_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    # Import here to avoid circular imports
    from ..config import get_api_key

    # Get API key from environment variable first, then from config
    key = os.environ.get("GEMINI_API_KEY") or get_api_key("gemini")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in environment or config")

    generation_config: dict = {"responseMimeType": "application/json"}
    if creativity is not None:
        generation_config["temperature"] = creativity

    prompt = LLM_PROMPT + json.dumps({"texts": texts}, ensure_ascii=False)

    def do_request():
        return http_session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.5-flash:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            },
            timeout=300,
        )

    def parse(resp):
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return extract_translations(raw)

    return call_with_retry("Gemini", do_request, parse)


ENGINES["gemini"] = EngineConfig(
    name="gemini",
    translate=gemini_translate,
    char_limit=20_000,
    elem_limit=50,
    delay=0,
)
