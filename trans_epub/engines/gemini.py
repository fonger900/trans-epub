"""Google Gemini translation engine.

Set GEMINI_API_KEY in your .env file.
Optionally set GEMINI_MODEL to override the model name.
Optionally set GEMINI_MAX_TOKENS to override max output tokens.
Optionally set GEMINI_TIMEOUT to override request timeout in seconds (default: 300).

Token usage tracking and cost estimation are built in — see _GEMINI_PRICING
for per-model rates (update when Google changes pricing).
"""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING

from .base import (
    ENGINES,
    EngineConfig,
    RateLimiter,
    build_prompt,
    call_with_retry,
    extract_translations,
    http_session,
)

if TYPE_CHECKING:
    from ..config import Glossary

_DEFAULT_MODEL = "gemini-3.1-flash-lite"
# _DEFAULT_MODEL = "gemini-3.1-pro-preview"

# ── Pricing (USD per 1M tokens) ────────────────────────────────────────────────
_GEMINI_PRICING: dict[str, tuple[float, float]] = {
    # Free tier
    "gemini-3.1-flash-lite": (0, 0),
    "gemini-2.5-flash-lite": (0, 0),
    # Flash
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3.1-flash": (0.15, 0.60),
    # Pro
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3.1-pro": (1.25, 10.00),
}

# ── Thread-safe token counters ─────────────────────────────────────────────────

_token_lock = threading.Lock()
_prompt_tokens: int = 0
_output_tokens: int = 0


def _accumulate_usage(body: dict) -> None:
    """Extract and accumulate token usage from a Gemini API response body."""
    usage = body.get("usageMetadata", {})
    if not usage:
        return
    global _prompt_tokens, _output_tokens
    with _token_lock:
        _prompt_tokens += usage.get("promptTokenCount", 0)
        _output_tokens += usage.get("candidatesTokenCount", 0)


def get_gemini_usage() -> tuple[int, int]:
    """Return accumulated (prompt_tokens, output_tokens)."""
    with _token_lock:
        return (_prompt_tokens, _output_tokens)


def reset_gemini_usage() -> None:
    """Reset token counters (call at start of each translation run)."""
    global _prompt_tokens, _output_tokens
    with _token_lock:
        _prompt_tokens = 0
        _output_tokens = 0


def _resolve_pricing(model: str) -> tuple[float, float]:
    """Resolve (input_price, output_price) for a model string."""
    if model in _GEMINI_PRICING:
        return _GEMINI_PRICING[model]
    for prefix in sorted(_GEMINI_PRICING, key=len, reverse=True):
        if model.startswith(prefix):
            return _GEMINI_PRICING[prefix]
    return (1.25, 10.00)


def estimate_gemini_cost(chars: int, model: str | None = None) -> float:
    """Estimate USD cost for translating *chars* characters of English text."""
    model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
    input_price, output_price = _resolve_pricing(model)
    input_tokens = chars / 3.0
    output_tokens = chars / 2.5
    return (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price


def actual_gemini_cost(model: str | None = None) -> float:
    """Calculate actual USD cost from accumulated token usage."""
    model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
    input_price, output_price = _resolve_pricing(model)
    prompt, output = get_gemini_usage()
    return (prompt / 1_000_000) * input_price + (output / 1_000_000) * output_price


# ── Safety settings ────────────────────────────────────────────────────────────

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


# ── Main translate function ────────────────────────────────────────────────────


def gemini_translate(
    texts: list[str],
    creativity: float | None = None,
    glossary: Glossary | None = None,
    extra_prompt: str = "",
) -> list[str]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in environment")

    model = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)

    generation_config: dict = {"responseMimeType": "application/json"}
    if creativity is not None:
        generation_config["temperature"] = creativity
    if max_tokens := os.environ.get("GEMINI_MAX_TOKENS"):
        generation_config["maxOutputTokens"] = int(max_tokens)

    prompt = build_prompt(glossary, extra_prompt) + json.dumps(
        {"texts": texts}, ensure_ascii=False
    )

    def do_request():
        return http_session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
                "safetySettings": _SAFETY_SETTINGS,
            },
            timeout=int(os.environ.get("GEMINI_TIMEOUT", "300")),
        )

    def parse(resp):
        body = resp.json()
        if "error" in body:
            raise ValueError(f"Gemini API error: {body['error']}")
        if "candidates" not in body or not body["candidates"]:
            finish_reason = None
            if "promptFeedback" in body:
                finish_reason = body["promptFeedback"].get("blockReason")
            raise ValueError(
                f"Gemini returned no candidates (blocked? {finish_reason})"
            )
        candidate = body["candidates"][0]
        if "finishReason" in candidate and candidate["finishReason"] != "STOP":
            raise ValueError(
                f"Gemini finish reason: {candidate['finishReason']} "
                f"(may indicate truncation — try increasing GEMINI_MAX_TOKENS)"
            )
        _accumulate_usage(body)
        raw = candidate["content"]["parts"][0]["text"]
        return extract_translations(raw)

    return call_with_retry(
        "Gemini", do_request, parse, limiter=ENGINES["gemini"].limiter
    )


ENGINES["gemini"] = EngineConfig(
    name="gemini",
    translate=gemini_translate,
    char_limit=20_000,
    elem_limit=50,
    delay=0,
    limiter=RateLimiter(rpm=15),
)
