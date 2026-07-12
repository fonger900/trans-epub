"""Alibaba Cloud Model Studio (DashScope) translation engine.

Set DASHSCOPE_API_KEY in your .env file.
Optionally set DASHSCOPE_API_BASE to override the API endpoint.
Optionally set DASHSCOPE_WORKSPACE_ID for custom workspace deployments.
Optionally set DASHSCOPE_MODEL to override the model name.
Optionally set DASHSCOPE_MAX_TOKENS to override the max token count (default: 8192).

Common models:
  - qwen-max (larger context, higher cost)
  - qwen-plus (balanced performance)
  - qwen-turbo (fast, economical)
  - qwen-mt-plus (optimized for machine translation tasks)

For custom workspaces, set DASHSCOPE_WORKSPACE_ID to your workspace ID.
If both DASHSCOPE_WORKSPACE_ID and DASHSCOPE_API_BASE are set, DASHSCOPE_API_BASE takes precedence.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from .base import (
    ENGINES,
    EngineConfig,
    build_prompt,
    call_with_retry,
    extract_translations,
    http_session,
)

if TYPE_CHECKING:
    from ..config import Glossary

DEFAULT_ALIBABA_CREATIVITY = 0.4
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-mt-plus"
_DEFAULT_MAX_TOKENS = 8192


def alibaba_translate(
    texts: list[str],
    creativity: float | None = None,
    glossary: Glossary | None = None,
    extra_prompt: str = "",
) -> list[str]:
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY not found in environment")

    # Determine the base URL - prioritize custom base URL, then workspace ID, then default
    custom_base = os.environ.get("DASHSCOPE_API_BASE")
    if custom_base:
        base_url = custom_base
    else:
        workspace_id = os.environ.get("DASHSCOPE_WORKSPACE_ID")
        if workspace_id:
            # Construct workspace-specific URL: https://ws-{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1
            # Try to extract region from a configured custom URL or default to ap-southeast-1
            default_workspace_region = "ap-southeast-1"
            base_url = f"https://ws-{workspace_id}.{default_workspace_region}.maas.aliyuncs.com/compatible-mode/v1"
        else:
            base_url = _DEFAULT_BASE_URL

    model = os.environ.get("DASHSCOPE_MODEL", _DEFAULT_MODEL)
    max_tokens = int(os.environ.get("DASHSCOPE_MAX_TOKENS", _DEFAULT_MAX_TOKENS))
    temperature = DEFAULT_ALIBABA_CREATIVITY if creativity is None else creativity

    prompt = build_prompt(glossary, extra_prompt) + json.dumps(
        {"texts": texts}, ensure_ascii=False
    )

    def do_request():
        return http_session.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=300,
        )

    def parse(resp):
        raw = resp.json()["choices"][0]["message"]["content"]
        return extract_translations(raw)

    return call_with_retry(
        "Alibaba", do_request, parse, limiter=ENGINES["alibaba"].limiter
    )


# Default configuration with conservative limits
ENGINES["alibaba"] = EngineConfig(
    name="alibaba",
    translate=alibaba_translate,
    char_limit=8_000,  # Reduced from 10k to ensure token limit compliance
    elem_limit=20,  # Reduced to prevent exceeding context window
    delay=0,
)
