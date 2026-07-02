"""DeepSeek translation engine."""

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

DEFAULT_DEEPSEEK_CREATIVITY = 0.4


def deepseek_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    # Import here to avoid circular imports
    from ..config import get_api_key

    # Get API key from environment variable first, then from config
    key = os.environ.get("DEEPSEEK_API_KEY") or get_api_key("deepseek")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not found in environment or config")

    temperature = DEFAULT_DEEPSEEK_CREATIVITY if creativity is None else creativity

    prompt = LLM_PROMPT + json.dumps({"texts": texts}, ensure_ascii=False)

    def do_request():
        return http_session.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 8192,
                "response_format": {"type": "json_object"},
            },
            timeout=300,
        )

    def parse(resp):
        raw = resp.json()["choices"][0]["message"]["content"]
        return extract_translations(raw)

    return call_with_retry("DeepSeek", do_request, parse)


ENGINES["deepseek"] = EngineConfig(
    name="deepseek",
    translate=deepseek_translate,
    char_limit=10_000,
    elem_limit=25,
    delay=0,
)
