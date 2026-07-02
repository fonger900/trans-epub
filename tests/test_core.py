"""Core functionality tests."""

import json
from unittest.mock import MagicMock, patch

from trans_epub.html_translator import translate_html


def test_translate_html_with_mock_engine():
    """Test HTML translation with mocked engine."""
    html_content = b"<html><body><p>Hello world</p></body></html>"

    # Mock the engine translation
    mock_translation_result = ["Xin chào thế giới"]

    def mock_translate_engine(texts, **kwargs):
        return mock_translation_result

    # Create a mock engine config
    mock_config = MagicMock()
    mock_config.char_limit = 1000
    mock_config.elem_limit = 10
    mock_config.delay = 0
    mock_config.translate = mock_translate_engine

    # Patch the ENGINES registry to return our mock config
    with patch("trans_epub.html_translator.ENGINES") as mock_engines:
        mock_engines.__getitem__.return_value = mock_config

        result, char_count = translate_html(html_content, "mock_engine")

        # Check that result contains translated content
        result_str = result.decode("utf-8")
        assert "Xin chào thế giới" in result_str
        assert char_count > 0


def test_translate_html_with_progress_callback():
    """Test HTML translation with progress callback."""
    html_content = b"<html><body><p>Hello world</p></body></html>"

    # Track progress callback calls
    progress_calls = []

    def progress_callback(batch_num, total_batches, batch_chars):
        progress_calls.append((batch_num, total_batches, batch_chars))

    # Mock the engine translation
    mock_translation_result = ["Xin chào thế giới"]

    def mock_translate_engine(texts, **kwargs):
        return mock_translation_result

    # Create a mock engine config
    mock_config = MagicMock()
    mock_config.char_limit = 1000
    mock_config.elem_limit = 10
    mock_config.delay = 0
    mock_config.translate = mock_translate_engine

    # Patch the ENGINES registry
    with patch("trans_epub.html_translator.ENGINES") as mock_engines:
        mock_engines.__getitem__.return_value = mock_config

        result, char_count = translate_html(
            html_content, "mock_engine", progress_cb=progress_callback
        )

        # Check that progress callback was called
        assert len(progress_calls) > 0
        # Verify callback arguments are reasonable
        batch_num, total_batches, batch_chars = progress_calls[0]
        assert isinstance(batch_num, int)
        assert isinstance(total_batches, int)
        assert isinstance(batch_chars, int)


def test_translate_html_empty_input():
    """Test HTML translation with empty input."""
    empty_html = b""

    # Mock the engine translation
    def mock_translate_engine(texts, **kwargs):
        return texts  # Return input as is for empty test

    # Create a mock engine config
    mock_config = MagicMock()
    mock_config.char_limit = 1000
    mock_config.elem_limit = 10
    mock_config.delay = 0
    mock_config.translate = mock_translate_engine

    # Patch the ENGINES registry
    with patch("trans_epub.html_translator.ENGINES") as mock_engines:
        mock_engines.__getitem__.return_value = mock_config

        result, char_count = translate_html(empty_html, "mock_engine")

        # Should return empty result with 0 character count
        assert result == empty_html
        assert char_count == 0


def test_translate_html_no_translatable_content():
    """Test HTML translation with no translatable content."""
    html_no_text = b'<html><body><img src="image.jpg" alt="" /></body></html>'

    # Mock the engine translation
    def mock_translate_engine(texts, **kwargs):
        # Should not be called since there are no translatable texts
        return []

    # Create a mock engine config
    mock_config = MagicMock()
    mock_config.char_limit = 1000
    mock_config.elem_limit = 10
    mock_config.delay = 0
    mock_config.translate = mock_translate_engine

    # Patch the ENGINES registry to verify the translation function is not called
    with patch("trans_epub.html_translator.ENGINES") as mock_engines:
        mock_engines.__getitem__.return_value = mock_config

        result, char_count = translate_html(html_no_text, "mock_engine")

        # Should return original content since no translatable text exists
        assert result == html_no_text
        assert char_count == 0
