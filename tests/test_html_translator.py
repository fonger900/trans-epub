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


class TestPreserveBlocks:
    """Verifies non-translatable blocks are not touched."""

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


class TestAttributeTranslation:
    """HTML attribute translation (alt, title, aria-label, placeholder)."""

    def test_translates_img_alt_inside_paragraph(
        self, mock_engines, mock_engine_config
    ):
        html = (
            b"<html><body>"
            b'<p>Look at <img alt="the red door" src="door.jpg"/> and smile</p>'
            b"</body></html>"
        )

        def capture(texts, **_kwargs):
            result = []
            for t in texts:
                if "red door" in t:
                    result.append(t.replace("the red door", "canh cua do"))
                else:
                    result.append("VI: " + t)
            return result

        mock_engine_config.translate = capture

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        assert 'alt="canh cua do"' in result_str
        assert "VI:" in result_str  # paragraph text also translated

    def test_translates_link_title(self, mock_engines, mock_engine_config):
        html = (
            b"<html><body>"
            b'<p>Click <a title="opens in new tab" href="x">here</a></p>'
            b"</body></html>"
        )

        def capture(texts, **_kwargs):
            return [t.replace("opens in new tab", "mo trong tab moi") for t in texts]

        mock_engine_config.translate = capture

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        assert 'title="mo trong tab moi"' in result_str

    def test_translates_aria_label(self, mock_engines, mock_engine_config):
        html = (
            b"<html><body>"
            b'<p><span aria-label="important note">!</span> Read this</p>'
            b"</body></html>"
        )

        def capture(texts, **_kwargs):
            return [t.replace("important note", "ghi chu quan trong") for t in texts]

        mock_engine_config.translate = capture

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        assert 'aria-label="ghi chu quan trong"' in result_str

    def test_skips_attributes_in_preserved_blocks(
        self, mock_engines, mock_engine_config
    ):
        html = (
            b"<html><body>"
            b'<div class="note">'
            b'<img alt="do not translate this" src="note.jpg"/>'
            b"</div>"
            b"<p>Hello</p>"
            b"</body></html>"
        )

        mock_engine_config.translate = lambda texts, **_kwargs: [
            "VI: " + t for t in texts
        ]

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        # alt in preserved block should NOT be translated
        assert 'alt="do not translate this"' in result_str
        # but paragraph text should be
        assert "VI: Hello" in result_str

    def test_standalone_img_alt_translated(self, mock_engines, mock_engine_config):
        """img tags outside text blocks still get alt translated."""
        html = (
            b"<html><body>"
            b'<img alt="Cover image" src="cover.jpg"/>'
            b"<p>Chapter 1</p>"
            b"</body></html>"
        )

        def capture(texts, **_kwargs):
            return [t.replace("Cover image", "Anh bia") for t in texts]

        mock_engine_config.translate = capture

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")

        assert 'alt="Anh bia"' in result_str

    def test_char_count_includes_attributes(self, mock_engines, mock_engine_config):
        html = (
            b"<html><body>"
            b"<p>Hello</p>"
            b'<img alt="a photo of a cat" src="cat.jpg"/>'
            b"</body></html>"
        )

        mock_engine_config.translate = lambda texts, **_kwargs: [
            "VI: " + t for t in texts
        ]

        _, char_count = translate_html(html, "test")
        # "Hello" (5) + "a photo of a cat" (16) = 21
        assert char_count == 21

    def test_duplicate_attributes_only_translated_once(
        self, mock_engines, mock_engine_config
    ):
        """Same img tag scanned twice (via node and standalone) should only translate once."""
        html = b'<html><body><p><img alt="unique" src="x.jpg"/></p></body></html>'

        seen_count = 0

        def count_seen(texts, **_kwargs):
            nonlocal seen_count
            seen_count += texts.count("unique")
            return texts

        mock_engine_config.translate = count_seen

        translate_html(html, "test")
        # "unique" should appear exactly once in the texts sent to API
        assert seen_count == 1


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
