"""Alibaba Cloud Model Studio (DashScope) translation engine.

Set DASHSCOPE_API_KEY in your .env file.
Optionally set DASHSCOPE_API_BASE to override the API endpoint.
Optionally set DASHSCOPE_MODEL to override the model name.
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

DEFAULT_ALIBABA_CREATIVITY = 0.4
_DEFAULT_BASE_URL = (
    "https://ws-s5gfqlikkiawofwj.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
)
_DEFAULT_MODEL = "qwen3.7-plus"


def alibaba_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["DASHSCOPE_API_KEY"]
    base_url = os.environ.get("DASHSCOPE_API_BASE", _DEFAULT_BASE_URL)
    model = os.environ.get("DASHSCOPE_MODEL", _DEFAULT_MODEL)
    temperature = DEFAULT_ALIBABA_CREATIVITY if creativity is None else creativity

    prompt = LLM_PROMPT + json.dumps({"texts": texts}, ensure_ascii=False)

    def do_request():
        return http_session.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
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

    return call_with_retry("Alibaba", do_request, parse)


ENGINES["alibaba"] = EngineConfig(
    name="alibaba",
    translate=alibaba_translate,
    char_limit=10_000,
    elem_limit=25,
    delay=0,
)
