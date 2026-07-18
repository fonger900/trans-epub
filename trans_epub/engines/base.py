"""
Shared infrastructure for all translation engines:
- http_session  (connection-pooled requests.Session)
- EngineConfig  (typed registry entry)
- LLM_PROMPT   (shared system prompt for LLM-based engines)
- extract_translations  (parse JSON from LLM output)
- call_with_retry  (shared retry logic for HTTP-based engines)
- ENGINES registry  (populated by each engine module)
"""

from __future__ import annotations

import ast
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import requests
from requests.adapters import HTTPAdapter

if TYPE_CHECKING:
    from ..config import Glossary

# ── Shared HTTP session ────────────────────────────────────────────────────────

_VERBOSE = False
_CURRENT_CHAPTER = ""  # set by process_chapter for error context
_CURRENT_CHAPTER_INFO = ""  # extra info like batch number

# Cancellation support — allows Ctrl+C to interrupt retry loops immediately
_cancel_event: threading.Event | None = None


def reset_cancel_event() -> None:
    """Create a fresh cancel event at start of each translation run."""
    global _cancel_event
    _cancel_event = threading.Event()


def request_cancel() -> None:
    """Signal all in-flight retry loops to abort immediately."""
    if _cancel_event:
        _cancel_event.set()


def is_cancelled() -> bool:
    """Check if user requested cancellation."""
    return _cancel_event is not None and _cancel_event.is_set()


def set_verbose(enabled: bool) -> None:
    """Enable or disable verbose request/retry logging."""
    global _VERBOSE
    _VERBOSE = enabled


def set_current_chapter(name: str) -> None:
    """Set current chapter name for error context in retry messages."""
    global _CURRENT_CHAPTER, _CURRENT_CHAPTER_INFO
    _CURRENT_CHAPTER = name
    _CURRENT_CHAPTER_INFO = ""


def set_current_chapter_info(info: str) -> None:
    """Append extra context like batch number to the current chapter label."""
    global _CURRENT_CHAPTER_INFO
    _CURRENT_CHAPTER_INFO = info


http_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
http_session.mount("https://", _adapter)
http_session.mount("http://", _adapter)

# ── Rate limiter ───────────────────────────────────────────────────────────────


class RateLimiter:
    """Thread-safe token-bucket limiter — prevents hitting API rate limits.

    Each engine shares one instance. Before every API call, ``wait()``
    sleeps until a request slot is available.
    """

    _interval: float
    _lock: threading.Lock
    _next: float

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / rpm  # seconds between requests
        self._lock = threading.Lock()
        self._next = 0.0  # earliest time next request is allowed

    def wait(self) -> None:
        """Block until a request slot is available."""
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


# ── Engine config ──────────────────────────────────────────────────────────────


@dataclass
class EngineConfig:
    """Configuration for a translation engine."""

    name: str
    translate: Callable[..., list[str]]
    char_limit: int
    elem_limit: int
    delay: float
    limiter: RateLimiter | None = None

    def __post_init__(self) -> None:
        if self.limiter is None and self.delay <= 0:
            # Default 10 RPM — safe for free tiers
            # Gemini free: 15 RPM, DeepSeek free: ~10 RPM
            self.limiter = RateLimiter(rpm=10)


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


def _repair_truncated_json(text: str) -> str:
    """Attempt to close unclosed JSON brackets/braces in truncated output."""
    # Count unclosed brackets/braces and append closing characters.
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    # Close any unclosed strings then close brackets/braces in reverse order.
    if in_string:
        text += '"'
    text += "".join(reversed(stack))
    return text


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
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            # Try json_repair (handles missing commas, trailing commas,
            # unescaped chars, truncation, etc.)
            try:
                from json_repair import repair_json

                data = json.loads(repair_json(repaired))
            except Exception:
                # Last resort: try to close truncated JSON, then ast.literal_eval
                try:
                    repaired2 = _repair_truncated_json(repaired)
                    data = json.loads(repaired2)
                except json.JSONDecodeError:
                    try:
                        data = ast.literal_eval(raw_json)
                    except Exception as e:
                        raise ValueError(
                            f"All JSON repair strategies failed: {e}"
                        ) from e

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
    limiter: RateLimiter | None = None,
) -> list[str]:
    """Execute an HTTP call with retry logic + proactive rate limiting.

    Args:
        engine_name: Label for error messages (e.g. "Alibaba").
        request_fn: Callable that performs the HTTP request and returns a Response.
        parse_fn: Callable that extracts translations from a successful Response.
                  May raise ValueError or json.JSONDecodeError to trigger a retry.
        max_attempts: Maximum number of attempts before giving up.
        limiter: Optional RateLimiter — if given, ``wait()`` is called before
                 each request to stay under RPM limits.
    """
    # Build context label for retry messages
    def _ctx():
        chapter = _CURRENT_CHAPTER
        info = _CURRENT_CHAPTER_INFO
        if chapter and info:
            return f"{engine_name} | {chapter} | {info}"
        if chapter:
            return f"{engine_name} | {chapter}"
        return engine_name

    for attempt in range(max_attempts):
        # Check for cancellation before each attempt
        if is_cancelled():
            raise KeyboardInterrupt("Translation cancelled by user")

        label = f"attempt {attempt + 1}/{max_attempts}"

        # Proactive: wait for rate limit slot before making request
        if limiter:
            limiter.wait()

        try:
            t0 = time.monotonic()
            resp = request_fn()
            elapsed = time.monotonic() - t0
            if _VERBOSE:
                print(
                    f"\n    [{_ctx()}] {label}: "
                    f"{resp.status_code} in {elapsed:.1f}s",
                    end="",
                    flush=True,
                )
        except requests.exceptions.RequestException as e:
            wait = min(3 * 2**attempt, 60)
            print(
                f"\n    [{_ctx()}] Request error ({label}): {e}. Retrying in {wait}s...",
                end=" ",
                flush=True,
            )
            if attempt == max_attempts - 1:
                raise
            # Interruptible sleep — breaks immediately on Ctrl+C
            if _cancel_event:
                if _cancel_event.wait(timeout=wait):
                    raise KeyboardInterrupt("Translation cancelled by user")
            else:
                time.sleep(wait)
            continue

        if resp.status_code == 429 or resp.status_code == 403:
            # Check for quota exceeded in response body
            resp_text = resp.text if isinstance(resp.text, str) else ""
            resp_text = resp_text.lower()
            quota_keywords = [
                "quota",
                "limit exceeded",
                "daily limit",
                "bandwidth",
                "usage exceeded",
                "rate limit",
                "insufficient quota",
                "billing",
                "payment required",
            ]
            is_quota_issue = any(kw in resp_text for kw in quota_keywords)

            if is_quota_issue:
                wait = min(int(resp.headers.get("Retry-After", 3 * 2**attempt)), 300)
                print(
                    f"\n    [{_ctx()}] Quota exceeded ({label}), waiting {wait}s... "
                    f"Check API quota or adjust creativity/char_limit.",
                    end=" ",
                    flush=True,
                )
            else:
                wait = min(int(resp.headers.get("Retry-After", 3 * 2**attempt)), 60)
                print(
                    f"\n    [{_ctx()}] Rate limited ({label}), waiting {wait}s...",
                    end=" ",
                    flush=True,
                )
            # Interruptible sleep
            if _cancel_event:
                if _cancel_event.wait(timeout=wait):
                    raise KeyboardInterrupt("Translation cancelled by user")
            else:
                time.sleep(wait)
            continue

        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            # 4xx (except 429) = bad request, retrying won't help
            body = (resp.text or "") or (
                resp.content.decode(errors="replace") if resp.content else ""
            )
            body = str(body)[:2000]
            reason = resp.reason or ""
            raise requests.exceptions.HTTPError(
                f"[{_ctx()}] {resp.status_code} ({label}): {reason}\n"
                f"Body: {body}",
                response=resp,
            )

        resp.raise_for_status()

        try:
            return parse_fn(resp)
        except Exception as e:
            print(
                f"\n    [{_ctx()}] Parse error ({label}): {e}. Retrying...",
                end=" ",
                flush=True,
            )
            if attempt == max_attempts - 1:
                raise
            continue

    raise RuntimeError(
        f"[{_ctx()}] translation failed after {max_attempts} attempts"
    )


def build_prompt(glossary: Glossary | None = None, extra_prompt: str = "") -> str:
    """Build full system prompt, optionally including glossary and extra instructions."""
    from ..config import build_glossary_prompt

    prompt = LLM_PROMPT
    if glossary:
        prompt += build_glossary_prompt(glossary)
    if extra_prompt:
        prompt += (
            "\nAdditional instructions for this book:\n" + extra_prompt.strip() + "\n"
        )
    return prompt


def translate_texts(
    engine: str,
    texts: list[str],
    creativity: float | None = None,
    glossary: Glossary | None = None,
    extra_prompt: str = "",
) -> list[str]:
    """Dispatch translation to the appropriate engine function."""
    cfg = ENGINES[engine]
    if engine in ("gemini", "deepseek", "alibaba"):
        return cfg.translate(
            texts, creativity=creativity, glossary=glossary, extra_prompt=extra_prompt
        )
    return cfg.translate(texts)
