"""
trans_epub — EPUB EN→VI translator package.

Public API:
  translate_epub   — translate an EPUB file
  translate_html   — translate a single HTML document (bytes)
  translate_toc_and_nav — translate TOC/nav in-place
  resolve_engine   — resolve 'auto' to a concrete engine name
  ENGINES          — engine registry dict
  main             — CLI entry point
  config           — glossary + pronoun matrix loader
  __version__      — version string
"""

from .cli import __version__, main, resolve_engine  # noqa: F401
from .config import load_glossary  # noqa: F401
from .engines.base import (  # noqa: F401
    ENGINES,
    EngineConfig,
    extract_translations,
    http_session,
    translate_texts,
)
from .epub_translator import get_spine_items, translate_epub  # noqa: F401
from .html_translator import (  # noqa: F401
    PRESERVE_CLASSES,
    PRESERVE_TAGS,
    TRANSLATE_TAGS,
    translate_html,
)
from .toc import translate_toc_and_nav  # noqa: F401
