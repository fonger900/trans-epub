"""Tests for TOC and nav-document translation."""

from unittest.mock import MagicMock, patch

import pytest
from ebooklib import epub

from trans_epub.engines import ENGINES, EngineConfig
from trans_epub.toc import translate_toc_and_nav


class TestTranslateToc:
    """translate_toc_and_nav with mocked book and engine."""

    @pytest.fixture
    def translate(self):
        """Return a mock translate function that prefixes with 'VI: '."""
        return lambda texts, **_kwargs: [f"VI: {t}" for t in texts]

    @pytest.fixture
    def engine_cfg(self, translate):
        return EngineConfig(
            name="test", translate=translate, char_limit=10_000, elem_limit=50, delay=0
        )

    def _make_link(self, title=None, children=None):
        link = MagicMock(spec=epub.Link)
        if title is not None:
            link.title = title
        else:
            del link.title
        link.content = children
        return link

    def test_translates_toc_titles(self, engine_cfg):
        link1 = self._make_link(title="Chapter 1")
        link2 = self._make_link(title="Chapter 2")
        book = MagicMock()
        book.toc = [link1, link2]
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {}
            translate_toc_and_nav(book, "test", cache)

        assert link1.title == "VI: Chapter 1"
        assert link2.title == "VI: Chapter 2"
        assert "__toc__" in cache

    def test_uses_cache_when_valid(self, engine_cfg):
        link = self._make_link(title="Chapter 1")
        book = MagicMock()
        book.toc = [link]
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {"__toc__": '["VI: Chapter 1"]'}
            translate_toc_and_nav(book, "test", cache)

        assert link.title == "VI: Chapter 1"

    def test_ignores_stale_cache(self, engine_cfg):
        link = self._make_link(title="Chapter 1")
        book = MagicMock()
        book.toc = [link]
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            # Cache has 2 items but only 1 title → length mismatch → re-translate
            cache = {"__toc__": '["Stale 1", "Stale 2"]'}
            translate_toc_and_nav(book, "test", cache)

        assert link.title == "VI: Chapter 1"

    def test_handles_nested_toc(self, engine_cfg):
        child = self._make_link(title="Child")
        parent = self._make_link(title="Parent", children=[child])
        book = MagicMock()
        book.toc = [parent]
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {}
            translate_toc_and_nav(book, "test", cache)

        assert parent.title == "VI: Parent"
        assert child.title == "VI: Child"

    def test_empty_toc(self, engine_cfg):
        book = MagicMock()
        book.toc = []
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {}
            translate_toc_and_nav(book, "test", cache)
            # No crash

    def test_links_without_title_skipped(self, engine_cfg):
        link_no_title = self._make_link()  # no title attr at all
        link_with_title = self._make_link(title="Has Title")
        book = MagicMock()
        book.toc = [link_no_title, link_with_title]
        book.get_items.return_value = []

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {}
            translate_toc_and_nav(book, "test", cache)

        assert link_with_title.title == "VI: Has Title"
        assert "__toc__" in cache


class TestTranslateNav:
    """Nav document translation within translate_toc_and_nav."""

    @pytest.fixture
    def translate(self):
        return lambda texts, **_kwargs: [f"VI: {t}" for t in texts]

    @pytest.fixture
    def engine_cfg(self, translate):
        return EngineConfig(
            name="test", translate=translate, char_limit=10_000, elem_limit=50, delay=0
        )

    def _make_nav_item(self, name="nav.xhtml", content=None):
        if content is None:
            content = (
                b'<html><body><nav><ol>'
                b'<li><a href="ch1.xhtml">Chapter 1</a></li>'
                b'</ol></nav></body></html>'
            )
        item = MagicMock(spec=epub.EpubNav)
        item.get_name.return_value = name
        item.get_content.return_value = content
        return item

    def test_translates_nav_document(self, engine_cfg):
        nav = self._make_nav_item()
        book = MagicMock()
        book.toc = []
        book.get_items.return_value = [nav]

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {}
            translate_toc_and_nav(book, "test", cache)

            # Nav content should have been set
            nav.set_content.assert_called_once()
            # Cache should have the nav
            assert nav.get_name() in cache

    def test_nav_uses_cache(self, engine_cfg):
        nav = self._make_nav_item()
        book = MagicMock()
        book.toc = []
        book.get_items.return_value = [nav]

        with patch.dict(ENGINES, {"test": engine_cfg}):
            cache = {nav.get_name(): "<translated/>"}
            translate_toc_and_nav(book, "test", cache)

            nav.set_content.assert_called_once_with(b"<translated/>")
