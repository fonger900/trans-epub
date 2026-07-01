"""DeepSeek translation engine."""

import json
import os
import time

from .base import ENGINES, extract_translations, http_session

DEFAULT_DEEPSEEK_CREATIVITY = 0.4

_PROMPT_PREFIX = (
    "You are a professional literary translator. Translate the following consecutive paragraphs of a book from English to Vietnamese.\n"
    "Guidelines:\n"
    "- The translation must sound natural, idiomatic, and fluent in Vietnamese (thuần Việt, thoát ý).\n"
    "- Do not translate literally (word-for-word). Adapt English idioms, passive voice, and complex structures to natural Vietnamese phrasing.\n"
    "- Maintain the tone, style, and flow of the original text across the paragraphs (they are in consecutive order).\n"
    "- Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order.\n\n"
)


def deepseek_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["DEEPSEEK_API_KEY"]
    temperature = DEFAULT_DEEPSEEK_CREATIVITY if creativity is None else creativity

    prompt = _PROMPT_PREFIX + json.dumps({"texts": texts}, ensure_ascii=False)

    for attempt in range(5):
        resp = http_session.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
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
ENGINES["deepseek"] = (deepseek_translate, 10_000, 25, 0)
