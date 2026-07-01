"""Google Gemini translation engine."""

import json
import os
import time

from .base import ENGINES, extract_translations, http_session

_PROMPT_PREFIX = (
    "You are a professional literary translator. Translate the following consecutive paragraphs of a book from English to Vietnamese.\n"
    "Guidelines:\n"
    "- The translation must sound natural, idiomatic, and fluent in Vietnamese (thuần Việt, thoát ý).\n"
    "- Do not translate literally (word-for-word). Adapt English idioms, passive voice, and complex structures to natural Vietnamese phrasing.\n"
    "- Maintain the tone, style, and flow of the original text across the paragraphs (they are in consecutive order).\n"
    "- Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order.\n\n"
)


def gemini_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["GEMINI_API_KEY"]
    generation_config: dict = {"responseMimeType": "application/json"}
    if creativity is not None:
        generation_config["temperature"] = creativity

    prompt = _PROMPT_PREFIX + json.dumps({"texts": texts}, ensure_ascii=False)

    for attempt in range(5):
        resp = http_session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            },
            timeout=120,
        )
        if resp.status_code == 429:
            wait = 2**attempt
            print(
                f"\n    429: {resp.json().get('error', {}).get('message', resp.text)}"
            )
            print(f"    Waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return extract_translations(raw)

    resp.raise_for_status()


# char_limit, elem_limit, inter-batch delay (seconds)
ENGINES["gemini"] = (gemini_translate, 20_000, 50, 0)
