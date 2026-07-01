"""
Import all engine modules so their ENGINES registrations run at package load time.
"""

from .azure import azure_translate  # noqa: F401
from .gemini import gemini_translate  # noqa: F401
from .deepseek import deepseek_translate  # noqa: F401
from .base import ENGINES, extract_translations, translate_texts, http_session  # noqa: F401
