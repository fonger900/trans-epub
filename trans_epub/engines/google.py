"""Google Cloud Translation v2 engine.

Set GOOGLE_TRANSLATE_API_KEY in your .env file or as an environment variable.
Optionally set GOOGLE_TRANSLATE_REGION to override the region (default: global).
"""

import os

from .base import ENGINES, EngineConfig, http_session


def google_translate(texts: list[str], **_kwargs) -> list[str]:
    # Import here to avoid circular imports
    from ..config import get_api_key

    key = os.environ.get("GOOGLE_TRANSLATE_API_KEY") or get_api_key("google")
    if not key:
        raise RuntimeError(
            "GOOGLE_TRANSLATE_API_KEY not found in environment or config"
        )

    region = os.environ.get("GOOGLE_TRANSLATE_REGION", "global")
    host = (
        "https://translation.googleapis.com/language/translate/v2"
        if region == "global"
        else f"https://{region}-translation.googleapis.com/language/translate/v2"
    )

    resp = http_session.post(
        f"{host}?key={key}",
        json={
            "q": texts,
            "source": "en",
            "target": "vi",
            "format": "text",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(
            f"Google Translate API error {data['error']['code']}: "
            f"{data['error']['message']}"
        )
    return [t["translatedText"] for t in data["data"]["translations"]]


ENGINES["google"] = EngineConfig(
    name="google",
    translate=google_translate,
    char_limit=30_000,
    elem_limit=100,
    delay=0,
)
