"""Alibaba Cloud Model Studio (DashScope) translation engine.

Set DASHSCOPE_API_KEY in your .env file.
Optionally set DASHSCOPE_API_BASE to override the API endpoint
  (default: https://dashscope.aliyuncs.com/compatible-mode/v1).
Optionally set DASHSCOPE_MODEL to override the model name
  (default: qwen-plus).
"""

import json
import os
import time

from .base import ENGINES, extract_translations, http_session

DEFAULT_ALIBABA_CREATIVITY = 0.4
_DEFAULT_BASE_URL = "https://ws-s5gfqlikkiawofwj.ap-southeast-1.maas.aliyuncs.com"
_DEFAULT_MODEL = "qwen-plus"

_PROMPT_PREFIX = (
    "You are a professional literary translator. Translate the following consecutive paragraphs of a book from English to Vietnamese.\n"
    "Guidelines:\n"
    "- The translation must sound natural, idiomatic, and fluent in Vietnamese (thuần Việt, thoát ý).\n"
    "- Do not translate literally (word-for-word). Adapt English idioms, passive voice, and complex structures to natural Vietnamese phrasing.\n"
    "- Maintain the tone, style, and flow of the original text across the paragraphs (they are in consecutive order).\n"
    "- Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order.\n\n"
)


def alibaba_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["DASHSCOPE_API_KEY"]
    base_url = os.environ.get("DASHSCOPE_API_BASE", _DEFAULT_BASE_URL)
    model = os.environ.get("DASHSCOPE_MODEL", _DEFAULT_MODEL)
    temperature = DEFAULT_ALIBABA_CREATIVITY if creativity is None else creativity

    prompt = _PROMPT_PREFIX + json.dumps({"texts": texts}, ensure_ascii=False)

    for attempt in range(5):
        resp = http_session.post(
            f"{base_url}/compatible-mode/v1",
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
            timeout=120,
        )
        if resp.status_code == 429:
            wait = 2**attempt
            print(f"\n    Rate limited, waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        try:
            return extract_translations(raw)
        except (json.JSONDecodeError, ValueError) as e:
            print(
                f"\n    JSON parse error (attempt {attempt + 1}): {e}. Retrying...",
                end=" ",
                flush=True,
            )
            if attempt == 4:
                raise
            continue

    resp.raise_for_status()


# char_limit, elem_limit, inter-batch delay (seconds)
ENGINES["alibaba"] = (alibaba_translate, 10_000, 25, 0)
