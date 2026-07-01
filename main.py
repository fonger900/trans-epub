"""
Thin shim — all logic now lives in the trans_epub package.

Kept for backward compatibility (python main.py ...) and so that
existing tests that import `main` still work without modification.
"""

from dotenv import load_dotenv

load_dotenv()

# Re-export everything the tests reference
from trans_epub import (  # noqa: E402, F401
    ENGINES,
    extract_translations,
    translate_texts,
    http_session,
    translate_html,
    translate_toc_and_nav,
    translate_epub,
    get_spine_items,
    resolve_engine,
    main,
)

# Individual engine functions (referenced by test_creativity.py)
from trans_epub.engines.gemini import gemini_translate  # noqa: F401
from trans_epub.engines.deepseek import deepseek_translate  # noqa: F401
from trans_epub.engines.azure import azure_translate  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
