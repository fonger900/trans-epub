"""Tests for HTML translation functionality."""

from unittest.mock import patch

from trans_epub.html_translator import translate_html


def _get_lovely_bones_html() -> bytes:
    """Extract the first chapter's HTML from The Lovely Bones EPUB."""
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub("tests/The Lovely Bones - Alice Sebold.epub.test")
    spine_ids = [idref for idref, _ in book.spine]
    by_id = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    # Item 7 (index_split_005.html) is the first chapter with actual text
    return by_id[spine_ids[6]].get_content()


def test_translate_html_basic():
    """Translate the first chapter of The Lovely Bones with a mock engine."""
    html_bytes = _get_lovely_bones_html()

    def mock_translate(texts, **_kwargs):
        return [f"VI: {t[:50]}..." if len(t) > 50 else f"VI: {t}" for t in texts]

    import trans_epub.engines

    mock_config = trans_epub.engines.EngineConfig(
        name="test",
        translate=mock_translate,
        char_limit=5_000,
        elem_limit=10,
        delay=0,
    )

    with patch.dict(trans_epub.engines.ENGINES, {"test_engine": mock_config}):
        result, char_count = translate_html(html_bytes, "test_engine")

    assert char_count > 0, "Should have translatable characters"
    assert isinstance(result, bytes)
    assert b"VI:" in result, "Translated content should appear in output"
    # Ensure non-translatable attributes like class names are preserved
    assert b'class="calibre1"' in result or b'class="calibre_3"' in result


def test_translate_html_preserves_structure():
    """Non-translatable block tags and note classes should be left untouched."""
    html = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        b"<p>Hello world</p>"
        b'<div class="note">Do not translate this note.</div>'
        b"<table><tr><td>Table cell</td></tr></table>"
        b"<style>body { color: red; }</style>"
        b"<p>Another paragraph</p>"
        b"</body></html>"
    )

    def mock_translate(texts, **_kwargs):
        return [f"VI[{t}]" for t in texts]

    import trans_epub.engines

    mock_config = trans_epub.engines.EngineConfig(
        name="test_preserve",
        translate=mock_translate,
        char_limit=5_000,
        elem_limit=10,
        delay=0,
    )

    with patch.dict(trans_epub.engines.ENGINES, {"test_preserve": mock_config}):
        result, _ = translate_html(html, "test_preserve")

    result_str = result.decode("utf-8")
    assert "VI[Hello world]" in result_str
    assert "VI[Another paragraph]" in result_str
    assert "Do not translate this note." in result_str
    assert "Table cell" in result_str  # tables are preserved
    assert "body { color: red; }" in result_str  # styles are preserved


def test_tags_constants():
    """Test that the HTML tag constants are properly defined."""
    from trans_epub.html_translator import (
        BLOCK_TAGS,
        PRESERVE_CLASSES,
        PRESERVE_TAGS,
        TRANSLATE_TAGS,
    )

    # Check that constants exist and are sets
    assert isinstance(TRANSLATE_TAGS, set)
    assert isinstance(PRESERVE_TAGS, set)
    assert isinstance(PRESERVE_CLASSES, set)
    assert isinstance(BLOCK_TAGS, set)

    # Check that they contain expected values
    assert "p" in TRANSLATE_TAGS
    assert "h1" in TRANSLATE_TAGS
    assert "table" in PRESERVE_TAGS
    assert "style" in PRESERVE_TAGS
    assert "note" in PRESERVE_CLASSES
