"""Tests for EPUB translation orchestration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trans_epub.epub_translator import _short_name, get_spine_items, translate_epub
from trans_epub.engines.base import ENGINES, EngineConfig


class TestShortName:
    """_short_name utility."""

    def test_returns_basename(self):
        assert _short_name("OEBPS/Text/ch01.xhtml") == "ch01.xhtml"

    def test_handles_deep_path(self):
        assert _short_name("a/b/c/d/file.xhtml") == "file.xhtml"

    def test_truncates_long_names(self):
        long_name = "a" * 50 + ".xhtml"
        result = _short_name(long_name)
        assert len(result) <= 30
        assert result.startswith("…")

    def test_short_name_unchanged(self):
        assert _short_name("short.xhtml") == "short.xhtml"


class TestGetSpineItems:
    """get_spine_items with mocked book."""

    def test_returns_spine_items_in_order(self):
        book = MagicMock()
        book.spine = [("id1", True), ("id2", True), ("id3", True)]

        item1 = MagicMock()
        item1.get_id.return_value = "id1"
        item2 = MagicMock()
        item2.get_id.return_value = "id2"
        item3 = MagicMock()
        item3.get_id.return_value = "id3"

        book.get_items_of_type.return_value = [item1, item2, item3]

        result = get_spine_items(book)
        assert result == [item1, item2, item3]

    def test_skips_missing_ids(self):
        book = MagicMock()
        book.spine = [("id1", True), ("missing_id", True), ("id2", True)]

        item1 = MagicMock()
        item1.get_id.return_value = "id1"
        item2 = MagicMock()
        item2.get_id.return_value = "id2"

        book.get_items_of_type.return_value = [item1, item2]

        result = get_spine_items(book)
        assert result == [item1, item2]

    def test_returns_empty_list_for_empty_spine(self):
        book = MagicMock()
        book.spine = []
        book.get_items_of_type.return_value = []
        assert get_spine_items(book) == []


class TestTranslateEpub:
    """translate_epub with mocked book and engine."""

    @pytest.fixture
    def mock_book(self):
        book = MagicMock()
        book.items = []
        book.spine = [("ch1", True), ("ch2", True)]
        book.toc = []

        ch1 = MagicMock()
        ch1.get_id.return_value = "ch1"
        ch1.get_name.return_value = "OEBPS/ch01.xhtml"
        ch1.get_content.return_value = b"<html><body><p>Hello</p></body></html>"

        ch2 = MagicMock()
        ch2.get_id.return_value = "ch2"
        ch2.get_name.return_value = "OEBPS/ch02.xhtml"
        ch2.get_content.return_value = b"<html><body><p>World</p></body></html>"

        book.get_items_of_type.return_value = [ch1, ch2]
        return book

    @pytest.fixture
    def mock_all(self, mock_book, tmp_path):
        input_path = str(tmp_path / "in.epub")
        output_path = str(tmp_path / "out.epub")

        def translate(texts, **_kwargs):
            return [f"VI: {t}" for t in texts]

        engine_cfg = EngineConfig(
            name="test", translate=translate, char_limit=10_000, elem_limit=50, delay=0
        )

        with (
            patch("trans_epub.epub_translator.epub.read_epub", return_value=mock_book),
            patch("trans_epub.epub_translator.epub.write_epub"),
            patch("trans_epub.epub_translator.translate_toc_and_nav"),
            patch("trans_epub.epub_translator._repack_epub"),
            patch.dict(ENGINES, {"test": engine_cfg}),
        ):
            yield input_path, output_path

    def test_translates_all_chapters(self, mock_all):
        input_path, output_path = mock_all
        translate_epub(input_path, output_path, engine="test")
        # Validates no crash with default params

    def test_only_chapters_restricts_work(self, mock_all):
        input_path, output_path = mock_all
        # Should not crash with only_chapters set
        translate_epub(input_path, output_path, engine="test", only_chapters={1})

    def test_list_only_does_not_translate(self, mock_all):
        input_path, output_path = mock_all
        with patch("trans_epub.epub_translator.console.print") as mock_print:
            translate_epub(input_path, output_path, engine="test", list_only=True)
            # New format includes char count column; just verify ch01 appears
            all_calls = " ".join(
                str(args[0]) for call in mock_print.call_args_list
                for args in call if args
            )
            assert "OEBPS/ch01.xhtml" in all_calls
            assert "5" in all_calls  # char count for "Hello"

    def test_engine_not_found(self, mock_all, capsys):
        input_path, output_path = mock_all
        translate_epub(input_path, output_path, engine="nonexistent")
        captured = capsys.readouterr()
        assert "failed" in captured.out
        assert "nonexistent" in captured.out

    def test_dry_run_does_not_make_api_calls(self, mock_all):
        """Dry run should scan and report but skip translation entirely."""
        input_path, output_path = mock_all
        with (
            patch(
                "trans_epub.epub_translator.translate_toc_and_nav"
            ) as mock_toc,
            patch(
                "trans_epub.epub_translator.translate_html"
            ) as mock_html,
        ):
            translate_epub(
                input_path, output_path, engine="test", dry_run=True
            )

        mock_toc.assert_not_called()
        mock_html.assert_not_called()
        assert not Path(output_path).exists()

    def test_verbose_flag_sets_module_var(self, mock_all):
        """--verbose should enable verbose mode in base module."""
        input_path, output_path = mock_all
        with patch("trans_epub.epub_translator.set_verbose") as mock_set:
            translate_epub(
                input_path, output_path, engine="test", verbose=True
            )
            mock_set.assert_called_once_with(True)

    def test_cache_survives_chapter_failure(self, mock_all, tmp_path):
        """If one chapter fails, cache should still save successful ones."""
        input_path, output_path = mock_all

        def flaky_translate(texts, **_kwargs):
            if texts == ["World"]:
                raise RuntimeError("API error on ch2")
            return ["VI: " + t for t in texts]

        cfg = EngineConfig(
            name="test",
            translate=flaky_translate,
            char_limit=10_000,
            elem_limit=50,
            delay=0,
        )

        # Build fresh mocks with known content
        book = MagicMock()
        book.items = []
        book.spine = [("ch1", True), ("ch2", True)]
        book.toc = []
        ch1 = MagicMock()
        ch1.get_id.return_value = "ch1"
        ch1.get_name.return_value = "ch01"
        ch1.get_content.return_value = b"<p>Hello</p>"
        ch2 = MagicMock()
        ch2.get_id.return_value = "ch2"
        ch2.get_name.return_value = "ch02"
        ch2.get_content.return_value = b"<p>World</p>"
        book.get_items_of_type.return_value = [ch1, ch2]

        engines_patch = patch.dict(ENGINES, dict(test=cfg))

        with (
            patch("trans_epub.epub_translator.epub.read_epub", return_value=book),
            patch("trans_epub.epub_translator.epub.write_epub"),
            patch("trans_epub.epub_translator.translate_toc_and_nav"),
            patch("trans_epub.epub_translator._repack_epub"),
            engines_patch,
        ):
            translate_epub(input_path, output_path, engine="test", threads=1)

        cache_path = Path(output_path + ".cache.json")
        assert cache_path.exists()
        cache = json.loads(cache_path.read_text())
        assert "ch01" in cache
        assert "VI: Hello" in cache["ch01"]
