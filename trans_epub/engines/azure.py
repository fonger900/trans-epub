"""Azure Cognitive Translator engine."""

import os
import uuid

from typing import Any

import requests

from .base import (
    ENGINES,
    EngineConfig,
    RateLimiter,
    call_with_retry,
    http_session,
)

_azure_limiter = RateLimiter(rpm=10)


def azure_translate(texts: list[str], **_kwargs: Any) -> list[str]:
    key = os.environ.get("AZURE_TRANSLATOR_KEY")
    if not key:
        raise RuntimeError("AZURE_TRANSLATOR_KEY not found in environment")

    region = os.environ.get("AZURE_TRANSLATOR_REGION", "global")

    def do_request():
        _azure_limiter.wait()
        return http_session.post(
            "https://api.cognitive.microsofttranslator.com/translate",
            params={"api-version": "3.0", "from": "en", "to": "vi"},
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Ocp-Apim-Subscription-Region": region,
                "Content-type": "application/json",
                "X-ClientTraceId": str(uuid.uuid4()),
            },
            json=[{"text": t} for t in texts],
            timeout=30,
        )

    def parse(resp: requests.Response) -> list[str]:
        return [r["translations"][0]["text"] for r in resp.json()]

    return call_with_retry("Azure", do_request, parse, max_attempts=8)


ENGINES["azure"] = EngineConfig(
    name="azure",
    translate=azure_translate,
    char_limit=40_000,
    elem_limit=100,
    delay=0,
)
