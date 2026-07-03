"""DeepL translation engine.

Set DEEPL_API_KEY in your .env file.
The free tier uses https://api-free.deepl.com, Pro uses https://api.deepl.com.
Set DEEPL_API_BASE to override the endpoint.
"""

import os

from .base import (
    ENGINES,
    EngineConfig,
    call_with_retry,
    http_session,
)

_DEFAULT_BASE = "https://api-free.deepl.com/v2/translate"


def deepl_translate(texts: list[str], **_kwargs) -> list[str]:
    # Import here to avoid circular imports
    from ..config import get_api_key

    key = os.environ.get("DEEPL_API_KEY") or get_api_key("deepl")
    if not key:
        raise RuntimeError("DEEPL_API_KEY not found in environment or config")

    base = os.environ.get("DEEPL_API_BASE", _DEFAULT_BASE)

    def do_request():
        return http_session.post(
            base,
            headers={
                "Authorization": f"DeepL-Auth-Key {key}",
                "Content-Type": "application/json",
            },
            json={
                "text": texts,
                "source_lang": "EN",
                "target_lang": "VI",
            },
            timeout=30,
        )

    def parse(resp):
        return [t["text"] for t in resp.json()["translations"]]

    return call_with_retry("DeepL", do_request, parse)


ENGINES["deepl"] = EngineConfig(
    name="deepl",
    translate=deepl_translate,
    char_limit=30_000,
    elem_limit=50,
    delay=0,
)
