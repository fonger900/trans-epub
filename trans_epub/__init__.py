"""
trans_epub — EPUB EN→VI translator package.

Public API:
  translate_epub   — translate an EPUB file
  translate_html   — translate a single HTML document (bytes)
  translate_toc_and_nav — translate TOC/nav in-place
  resolve_engine   — resolve 'auto' to a concrete engine name
  ENGINES          — engine registry dict
  main             — CLI entry point
"""

from .engines import ENGINES, extract_translations, translate_texts, http_session  # noqa: F401
from .html_translator import translate_html, TRANSLATE_TAGS, PRESERVE_TAGS, PRESERVE_CLASSES  # noqa: F401
from .toc import translate_toc_and_nav  # noqa: F401
from .epub_translator import translate_epub, get_spine_items  # noqa: F401
from .cli import main, resolve_engine  # noqa: F401
