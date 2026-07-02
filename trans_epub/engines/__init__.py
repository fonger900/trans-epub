"""
Import all engine modules so their ENGINES registrations run at package load time.
"""

from .alibaba import alibaba_translate  # noqa: F401
from .azure import azure_translate  # noqa: F401
from .base import (  # noqa: F401
    ENGINES,
    extract_translations,
    http_session,
    translate_texts,
)
from .deepseek import deepseek_translate  # noqa: F401
from .gemini import gemini_translate  # noqa: F401
