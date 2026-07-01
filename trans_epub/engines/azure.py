"""Azure Cognitive Translator engine."""

import os
import time
import uuid

from .base import ENGINES, http_session


def azure_translate(texts: list[str]) -> list[str]:
    key = os.environ["AZURE_TRANSLATOR_KEY"]
    region = os.environ.get("AZURE_TRANSLATOR_REGION", "global")

    for attempt in range(8):
        resp = http_session.post(
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
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2**attempt))
            print(f"\n    Rate limited, waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return [r["translations"][0]["text"] for r in resp.json()]

    resp.raise_for_status()


# char_limit, elem_limit, inter-batch delay (seconds)
ENGINES["azure"] = (azure_translate, 40_000, 100, 1.5)
