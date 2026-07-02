"""
Shared infrastructure for all translation engines:
- http_session  (connection-pooled requests.Session)
- EngineConfig  (typed registry entry)
- LLM_PROMPT   (shared system prompt for LLM-based engines)
- extract_translations  (parse JSON from LLM output)
- call_with_retry  (shared retry logic for HTTP-based engines)
- ENGINES registry  (populated by each engine module)
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Callable

import requests
from requests.adapters import HTTPAdapter

# ── Shared HTTP session ────────────────────────────────────────────────────────

http_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
http_session.mount("https://", _adapter)
http_session.mount("http://", _adapter)

# ── Engine config ──────────────────────────────────────────────────────────────


@dataclass
class EngineConfig:
    """Configuration for a translation engine."""

    name: str
    translate: Callable
    char_limit: int
    elem_limit: int
    delay: float


ENGINES: dict[str, EngineConfig] = {}

# ── Shared LLM prompt ─────────────────────────────────────────────────────────

# Inline emphasis tags kept in the text sent to (and expected back from) the LLM.
# Single source of truth: html_translator imports this, and the prompt below is
# built from it.
EMPHASIS_TAGS = {"em", "strong", "b", "i"}

_EMPHASIS_LIST = ", ".join(f"<{t}>" for t in sorted(EMPHASIS_TAGS))

LLM_PROMPT = (
    "You are a professional literary translator. Translate the following consecutive "
    "paragraphs of a book from English to Vietnamese.\n"
    "Guidelines:\n"
    "- The translation must sound natural, idiomatic, and fluent in Vietnamese "
    "(thuần Việt, thoát ý).\n"
    "- Do not translate literally (word-for-word). Adapt English idioms, passive "
    "voice, and complex structures to natural Vietnamese phrasing.\n"
    "- Maintain the tone, style, and flow of the original text across the paragraphs "
    "(they are in consecutive order).\n"
    f"- Some texts contain HTML emphasis tags ({_EMPHASIS_LIST}). "
    "Keep those tags in your translation, placed around the equivalent emphasized "
    "words or phrases. Do not add, remove, or change any other HTML tags, and do "
    "not wrap the translation in a paragraph or block tag.\n"
    "- Return a JSON object with a single key 'translations' containing the array of "
    "translated strings in the exact same order.\n\n"
)

# ── Shared utilities ───────────────────────────────────────────────────────────


def extract_translations(raw_json: str) -> list[str]:
    """Parse a JSON translation response from an LLM, repairing common issues."""
    raw_json = (
        raw_json.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # DeepSeek sometimes emits raw control characters (literal newlines/tabs)
        # inside JSON string values instead of escaping them.
        repaired = re.sub(
            r"(?<!\\)[\x00-\x1f]",
            lambda m: {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(m.group(0), ""),
            raw_json,
        )
        data = json.loads(repaired)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "translations" in data:
            return data["translations"]
        for v in data.values():
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and "translations" in v:
                return v["translations"]
    raise ValueError("Invalid JSON translation response format")


def call_with_retry(
    engine_name: str,
    request_fn: Callable[[], requests.Response],
    parse_fn: Callable[[requests.Response], list[str]],
    max_attempts: int = 7,
) -> list[str]:
    """Execute an HTTP call with retry logic for network errors, 429s, and parse failures.

    Args:
        engine_name: Label for error messages (e.g. "Alibaba").
        request_fn: Callable that performs the HTTP request and returns a Response.
        parse_fn: Callable that extracts translations from a successful Response.
                  May raise ValueError or json.JSONDecodeError to trigger a retry.
        max_attempts: Maximum number of attempts before giving up.
    """
    for attempt in range(max_attempts):
        label = f"attempt {attempt + 1}/{max_attempts}"
        try:
            resp = request_fn()
        except requests.exceptions.RequestException as e:
            wait = min(3 * 2**attempt, 60)
            print(
                f"\n    Request error ({label}): {e}. Retrying in {wait}s...",
                end=" ",
                flush=True,
            )
            if attempt == max_attempts - 1:
                raise
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            wait = min(int(resp.headers.get("Retry-After", 3 * 2**attempt)), 60)
            print(
                f"\n    Rate limited ({label}), waiting {wait}s...", end=" ", flush=True
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()

        try:
            return parse_fn(resp)
        except (json.JSONDecodeError, ValueError) as e:
            print(
                f"\n    JSON parse error ({label}): {e}. Retrying...",
                end=" ",
                flush=True,
            )
            if attempt == max_attempts - 1:
                raise
            continue

    raise RuntimeError(f"{engine_name} translation failed: all retries exhausted")


def translate_texts(
    engine: str, texts: list[str], creativity: float | None = None
) -> list[str]:
    """Dispatch translation to the appropriate engine function."""
    cfg = ENGINES[engine]
    if engine in ("gemini", "deepseek", "alibaba"):
        return cfg.translate(texts, creativity=creativity)
    return cfg.translate(texts)
