"""
Shared infrastructure for all translation engines:
- http_session  (connection-pooled requests.Session)
- extract_translations  (parse JSON from LLM output)
- ENGINES registry  (populated by each engine module)
- translate_texts  (dispatch helper)
"""

import json
import re
import time

import requests

# ── Shared HTTP session ────────────────────────────────────────────────────────

http_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
http_session.mount("https://", _adapter)
http_session.mount("http://", _adapter)

# ── Engine registry ────────────────────────────────────────────────────────────
# Each entry: name -> (translate_fn, char_limit, elem_limit, delay)
ENGINES: dict[str, tuple] = {}

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
    raise ValueError("Invalid JSON translation response format")


def translate_texts(
    engine: str, texts: list[str], creativity: float | None = None
) -> list[str]:
    """Dispatch translation to the appropriate engine function."""
    translate_fn, _, _, _ = ENGINES[engine]
    if engine in ("gemini", "deepseek", "alibaba"):
        return translate_fn(texts, creativity=creativity)
    return translate_fn(texts)


def retry_rate_limited(resp, attempt: int, label: str) -> int:
    """Handle 429 responses. Returns the wait time used (for callers that need it)."""
    wait = int(resp.headers.get("Retry-After", 2**attempt))
    print(f"\n    {label}: Rate limited, waiting {wait}s...", end=" ", flush=True)
    time.sleep(wait)
    return wait
