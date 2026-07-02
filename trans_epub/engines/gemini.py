"""Google Gemini translation engine.

Set GEMINI_API_KEY in your .env file.
Optionally set GEMINI_MODEL to override the model name.
Optionally set GEMINI_MAX_TOKENS to override max output tokens.
"""

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

_DEFAULT_MODEL = "gemini-3.5-flash"

# Permit all safety categories so Gemini doesn't block literary content
_SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_NONE"}
    for c in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
        "HARM_CATEGORY_CIVIC_INTEGRITY",
    )
]


def gemini_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    # Import here to avoid circular imports
    from ..config import get_api_key

    key = os.environ.get("GEMINI_API_KEY") or get_api_key("gemini")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in environment or config")

    model = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)

    generation_config: dict = {"responseMimeType": "application/json"}
    if creativity is not None:
        generation_config["temperature"] = creativity
    if max_tokens := os.environ.get("GEMINI_MAX_TOKENS"):
        generation_config["maxOutputTokens"] = int(max_tokens)

    prompt = LLM_PROMPT + json.dumps({"texts": texts}, ensure_ascii=False)

    def do_request():
        return http_session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
                "safetySettings": _SAFETY_SETTINGS,
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
