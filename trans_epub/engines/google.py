"""Google Cloud Translation v2 engine.

Set GOOGLE_TRANSLATE_API_KEY in your .env file or as an environment variable.
Optionally set GOOGLE_TRANSLATE_REGION to override the region (default: global).
"""

import os

from typing import Any

import requests

from .base import (
    ENGINES,
    EngineConfig,
    call_with_retry,
    http_session,
)


def google_translate(texts: list[str], **_kwargs: Any) -> list[str]:
    key = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_TRANSLATE_API_KEY not found in environment")

    region = os.environ.get("GOOGLE_TRANSLATE_REGION", "global")
    host = (
        "https://translation.googleapis.com/language/translate/v2"
        if region == "global"
        else f"https://{region}-translation.googleapis.com/language/translate/v2"
    )

    def do_request():
        return http_session.post(
            f"{host}?key={key}",
            json={
                "q": texts,
                "source": "en",
                "target": "vi",
                "format": "text",
            },
            timeout=30,
        )

    def parse(resp: requests.Response) -> list[str]:
        data = resp.json()
        if "error" in data:
            raise RuntimeError(
                f"Google Translate API error {data['error']['code']}: "
                f"{data['error']['message']}"
            )
        return [t["translatedText"] for t in data["data"]["translations"]]

    return call_with_retry("Google", do_request, parse)


ENGINES["google"] = EngineConfig(
    name="google",
    translate=google_translate,
    char_limit=30_000,
    elem_limit=100,
    delay=0,
)
