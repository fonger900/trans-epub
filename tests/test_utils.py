"""Tests for utility functions: cache helpers, rate limiter, char counting."""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from trans_epub.engines.base import RateLimiter
from trans_epub.epub_translator import _load_cache, _save_cache, _CACHE_HASH_KEY
from trans_epub.html_translator import count_translatable_chars
from trans_epub.toc import _is_toc_candidate, _toc_href_to_relative


# ── _load_cache ──────────────────────────────────────────────────────────────

class TestLoadCache:
    def test_returns_empty_when_fresh(self, tmp_path):
        cache_path = tmp_path / "test.cache.json"
        cache_path.write_text('{"key": "value"}')
        result = _load_cache(cache_path, "input.epub", fresh=True)
        assert result == {}

    def test_returns_empty_when_missing(self, tmp_path):
        cache_path = tmp_path / "nonexistent.cache.json"
        result = _load_cache(cache_path, "input.epub", fresh=False)
        assert result == {}

    def test_loads_valid_cache(self, tmp_path):
        cache_path = tmp_path / "test.cache.json"
        cache_path.write_text('{"ch01": "translated", "__epub_hash__": "abc123"}')
        result = _load_cache(cache_path, "input.epub", fresh=False)
        assert result == {"ch01": "translated"}
        # Hash key should be popped out

    def test_corrupted_json_returns_empty(self, tmp_path):
        cache_path = tmp_path / "test.cache.json"
        cache_path.write_text("not valid json {{{")
        result = _load_cache(cache_path, "input.epub", fresh=False)
        assert result == {}

    def test_invalid_type_returns_empty(self, tmp_path):
        cache_path = tmp_path / "test.cache.json"
        cache_path.write_text("[1, 2, 3]")  # list, not dict
        result = _load_cache(cache_path, "input.epub", fresh=False)
        assert result == {}

    def test_warns_when_epub_hash_changes(self, tmp_path):
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("original content")
        cache_path = tmp_path / "test.cache.json"
        cache_data = {"ch01": "old translation", _CACHE_HASH_KEY: "oldhash"}
        cache_path.write_text(json.dumps(cache_data))

        with patch("trans_epub.epub_translator.console.print") as mock_print:
            result = _load_cache(cache_path, str(epub_path), fresh=False)

        assert result == {"ch01": "old translation"}
        # Should have warned about changed EPUB
        warning_calls = [
            str(args[0])
            for call in mock_print.call_args_list
            for args in call
            if args and "changed" in str(args[0]).lower()
        ]
        assert len(warning_calls) > 0

    def test_no_warning_when_first_run_no_hash(self, tmp_path):
        """When cache has no hash (first run), no warning should appear."""
        cache_path = tmp_path / "test.cache.json"
        cache_path.write_text('{"ch01": "translated"}')  # no hash key

        with patch("trans_epub.epub_translator.console.print") as mock_print:
            result = _load_cache(cache_path, "nonexistent.epub", fresh=False)

        assert result == {"ch01": "translated"}
        warning_calls = [
            str(args[0])
            for call in mock_print.call_args_list
            for args in call
            if args and "changed" in str(args[0]).lower()
        ]
        assert len(warning_calls) == 0


# ── _save_cache ──────────────────────────────────────────────────────────────

class TestSaveCache:
    def test_stores_hash_when_epub_exists(self, tmp_path):
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("book content")
        cache_path = tmp_path / "test.cache.json"
        cache = {"ch01": "translated"}

        _save_cache(cache_path, cache, str(epub_path))

        saved = json.loads(cache_path.read_text())
        assert saved["ch01"] == "translated"
        assert _CACHE_HASH_KEY in saved
        # Original cache dict should NOT have the hash key (it's popped)
        assert _CACHE_HASH_KEY not in cache

    def test_handles_missing_epub_gracefully(self, tmp_path):
        cache_path = tmp_path / "test.cache.json"
        cache = {"ch01": "translated"}

        _save_cache(cache_path, cache, "/nonexistent/path.epub")

        saved = json.loads(cache_path.read_text())
        assert saved["ch01"] == "translated"
        # Hash key should not be present since EPUB doesn't exist
        assert _CACHE_HASH_KEY not in saved

    def test_original_cache_unmodified_except_hash(self, tmp_path):
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        cache_path = tmp_path / "test.cache.json"
        cache = {"ch01": "t1", "ch02": "t2"}

        _save_cache(cache_path, cache, str(epub_path))

        # After save, the original dict should be clean
        assert cache == {"ch01": "t1", "ch02": "t2"}

    def test_atomic_write_no_temp_file_left(self, tmp_path):
        """Temp file should be cleaned up after atomic write."""
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        cache_path = tmp_path / "test.cache.json"
        cache = {"ch01": "t1"}

        _save_cache(cache_path, cache, str(epub_path))

        # Main cache file should exist
        assert cache_path.exists()
        saved = json.loads(cache_path.read_text())
        assert saved["ch01"] == "t1"
        # Temp file should NOT exist
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        assert not tmp_path.exists()

    def test_atomic_write_survives_existing_temp(self, tmp_path):
        """Stale temp file from previous crash should not break save."""
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        cache_path = tmp_path / "test.cache.json"
        tmp_file = cache_path.with_suffix(cache_path.suffix + ".tmp")

        # Simulate stale temp file from previous crash
        tmp_file.write_text("garbage")

        cache = {"ch01": "fresh"}
        _save_cache(cache_path, cache, str(epub_path))

        # Should overwrite stale temp and produce valid cache
        saved = json.loads(cache_path.read_text())
        assert saved["ch01"] == "fresh"
        assert not tmp_file.exists()


# ── RateLimiter ───────────────────────────────────────────────────────────────

class TestRateLimiter:
    def test_first_call_does_not_sleep(self):
        limiter = RateLimiter(rpm=60)  # 1 per second
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1  # first call should be instant

    def test_subsequent_call_waits(self):
        limiter = RateLimiter(rpm=120)  # 2 per second = 0.5s interval
        limiter.wait()
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        # Second call should wait ~0.5s
        assert 0.3 < elapsed < 0.8

    def test_concurrent_threads_do_not_exceed_rate(self):
        """Multiple threads hammering wait() concurrently respect the RPM limit."""
        limiter = RateLimiter(rpm=20)  # 3s between calls
        results = []
        lock = threading.Lock()
        errors = []

        def worker():
            try:
                t0 = time.monotonic()
                limiter.wait()
                elapsed = time.monotonic() - t0
                with lock:
                    results.append(elapsed)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_elapsed = time.monotonic() - t_start

        # 5 calls at 20 RPM (3s each) should take at least ~12s total elapsed
        assert total_elapsed > 8
        assert len(errors) == 0

    def test_default_interval_for_free_tier(self):
        """Default 10 RPM should give ~6s interval."""
        limiter = RateLimiter(rpm=10)
        assert 5.9 < limiter._interval < 6.1


# ── count_translatable_chars ─────────────────────────────────────────────────

class TestCountTranslatableChars:
    def test_basic_paragraph(self):
        html = b"<html><body><p>Hello world</p></body></html>"
        assert count_translatable_chars(html) == 11  # "Hello world"

    def test_empty_input(self):
        assert count_translatable_chars(b"") == 0

    def test_no_translatable_tags(self):
        html = b'<html><body><img src="x.jpg"/><br/></body></html>'
        assert count_translatable_chars(html) == 0

    def test_multiple_paragraphs(self):
        html = b"<html><body><p>One</p><p>Two</p></body></html>"
        assert count_translatable_chars(html) == 6  # "One" + "Two"

    def test_preserved_blocks_excluded(self):
        html = (
            b"<html><body>"
            b"<p>Hello</p>"
            b'<div class="note">Skip me</div>'
            b"<p>World</p>"
            b"</body></html>"
        )
        # "Hello" + "World" = 10, "Skip me" excluded
        assert count_translatable_chars(html) == 10

    def test_nested_block_tags_excluded(self):
        """Paragraphs inside tables/blocks should not be counted."""
        html = (
            b"<html><body>"
            b"<p>Count me</p>"
            b"<table><tr><td>Skip table</td></tr></table>"
            b"</body></html>"
        )
        assert count_translatable_chars(html) == 8  # only "Count me"

    def test_emphasis_tags_counted(self):
        html = b"<html><body><p>Hello <em>world</em></p></body></html>"
        # Emphasis tags ARE included in the text sent to API, so they count too.
        # "Hello <em>world</em>" = 20 characters
        assert count_translatable_chars(html) == 20

    def test_non_utf8_content(self):
        """Content with non-UTF8 bytes should still be countable."""
        # lxml parser handles encoding from XML declaration
        html = (
            b'<?xml version="1.0" encoding="iso-8859-1"?>'
            b"<html><body><p>"
            b"caf\xe9"  # café in latin-1
            b"</p></body></html>"
        )
        count = count_translatable_chars(html)
        assert count >= 3  # at minimum "caf"


# ── TOC helpers ──────────────────────────────────────────────────────────────

class TestTocHrefToRelative:
    def test_matches_toc_dir_prefix(self):
        result = _toc_href_to_relative("OEBPS/Text/ch01.xhtml", "OEBPS/Text/")
        assert result == "ch01.xhtml"

    def test_no_match_returns_basename(self):
        result = _toc_href_to_relative("OEBPS/Text/ch01.xhtml", "other/")
        assert result == "ch01.xhtml"

    def test_empty_toc_dir_returns_basename(self):
        result = _toc_href_to_relative("OEBPS/Text/ch01.xhtml", "")
        assert result == "ch01.xhtml"

    def test_basename_only(self):
        result = _toc_href_to_relative("ch01.xhtml", "")
        assert result == "ch01.xhtml"


class TestIsTocCandidate:
    def test_chapter_pattern(self):
        # _c0 pattern matches chapter files like _c001.xhtml, _c002.xhtml
        assert _is_toc_candidate("Text/_c001.xhtml")
        assert _is_toc_candidate("_c042.xhtml")

    def test_acknowledgments(self):
        assert _is_toc_candidate("Text/_ack.xhtml")

    def test_appendix(self):
        assert _is_toc_candidate("Text/_app_a.xhtml")

    def test_index(self):
        assert _is_toc_candidate("Text/_idx.xhtml")

    def test_dedication(self):
        assert _is_toc_candidate("Text/_ded.xhtml")

    def test_notes(self):
        assert _is_toc_candidate("Text/_nts.xhtml")

    def test_non_toc_items(self):
        assert not _is_toc_candidate("cover.xhtml")
        assert not _is_toc_candidate("titlepage.xhtml")
        assert not _is_toc_candidate("copyright.xhtml")
