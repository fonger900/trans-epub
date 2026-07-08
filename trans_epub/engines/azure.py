"""Azure Cognitive Translator engine."""

import os
import threading
import time
import uuid

from .base import (
    ENGINES,
    EngineConfig,
    call_with_retry,
    http_session,
)


class _AzureRateLimiter:
    """Thread-safe rate limiter: ensures at least *interval* seconds between calls."""

    def __init__(self, interval: float):
        self._interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


_azure_limiter = _AzureRateLimiter(6.0)  # Azure free tier: ~10 req/min


def azure_translate(texts: list[str], **_kwargs) -> list[str]:
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

    def parse(resp):
        return [r["translations"][0]["text"] for r in resp.json()]

    return call_with_retry("Azure", do_request, parse, max_attempts=8)


ENGINES["azure"] = EngineConfig(
    name="azure",
    translate=azure_translate,
    char_limit=40_000,
    elem_limit=100,
    delay=0,
)
