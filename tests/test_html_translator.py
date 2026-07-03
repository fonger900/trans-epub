"""Tests for HTML translation — structure preservation and real EPUB fixture."""

from trans_epub.html_translator import (
    BLOCK_TAGS,
    PRESERVE_CLASSES,
    PRESERVE_TAGS,
    TRANSLATE_TAGS,
    translate_html,
)


def _get_sample_chapter_html() -> bytes:
    """Extract the first chapter from The Lovely Bones test EPUB."""
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub("tests/The Lovely Bones - Alice Sebold.epub.test")
    spine_ids = [idref for idref, _ in book.spine]
    by_id = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    return by_id[spine_ids[6]].get_content()


class TestWithRealEpub:
    """Tests using an actual EPUB chapter to verify real-world behaviour."""

    def test_basic(self, mock_engines, mock_engine_config):
        html_bytes = _get_sample_chapter_html()

        def cap_texts(texts, **_kwargs):
            return [f"VI: {t[:50]}..." if len(t) > 50 else f"VI: {t}" for t in texts]

        mock_engine_config.translate = cap_texts
        result, char_count = translate_html(html_bytes, "test")

        assert char_count > 0
        assert isinstance(result, bytes)
        assert b"VI:" in result
        assert b'class="calibre1"' in result or b'class="calibre_3"' in result

    def test_preserves_non_translatable_blocks(self, mock_engines, mock_engine_config):
        html = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            b"<p>Hello world</p>"
            b'<div class="note">Do not translate this note.</div>'
            b"<table><tr><td>Table cell</td></tr></table>"
            b"<style>body { color: red; }</style>"
            b"<p>Another paragraph</p>"
            b"</body></html>"
        )

        mock_engine_config.translate = lambda texts, **_kwargs: [
            f"VI[{t}]" for t in texts
        ]
        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        assert "VI[Hello world]" in result_str
        assert "VI[Another paragraph]" in result_str
        assert "Do not translate this note." in result_str
        assert "Table cell" in result_str
        assert "body { color: red; }" in result_str


class TestTagConstants:
    """Tag-set constants are correctly defined."""

    def test_translate_tags(self):
        assert "p" in TRANSLATE_TAGS
        assert "h1" in TRANSLATE_TAGS
        assert "td" in TRANSLATE_TAGS

    def test_preserve_tags(self):
        assert "table" in PRESERVE_TAGS
        assert "style" in PRESERVE_TAGS

    def test_preserve_classes(self):
        assert "note" in PRESERVE_CLASSES

    def test_block_tags_match_translate_tags(self):
        assert BLOCK_TAGS == TRANSLATE_TAGS
