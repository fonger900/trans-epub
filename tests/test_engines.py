"""Tests for translation engines."""

import os
from unittest.mock import MagicMock, patch

import pytest

from trans_epub.engines import ENGINES
from trans_epub.engines.base import EngineConfig, call_with_retry, extract_translations


def test_engines_registered():
    """Test that all expected engines are registered."""
    expected_engines = {"azure", "alibaba", "gemini", "deepseek", "google"}
    registered_engines = set(ENGINES.keys())

    assert expected_engines.issubset(registered_engines), (
        f"Missing engines: {expected_engines - registered_engines}"
    )


def test_engine_config_structure():
    """Test that engine configs have expected structure."""
    for name, config in ENGINES.items():
        assert hasattr(config, "name")
        assert hasattr(config, "translate")
        assert hasattr(config, "char_limit")
        assert hasattr(config, "elem_limit")
        assert hasattr(config, "delay")

        # Check that properties have expected types
        assert isinstance(config.name, str)
        assert callable(config.translate)
        assert isinstance(config.char_limit, int)
        assert isinstance(config.elem_limit, int)
        assert isinstance(config.delay, (int, float))


def test_extract_translations_basic():
    """Test basic JSON translation extraction."""
    json_str = '{"translations": ["Xin chào", "Thế giới"]}'
    result = extract_translations(json_str)
    assert result == ["Xin chào", "Thế giới"]


def test_extract_translations_with_prefix_suffix():
    """Test extraction with markdown prefix/suffix."""
    json_str = '```json\n{"translations": ["Xin chào", "Thế giới"]}\n```'
    result = extract_translations(json_str)
    assert result == ["Xin chào", "Thế giới"]


def test_extract_translations_list_format():
    """Test extraction from list format."""
    json_str = '["Xin chào", "Thế giới"]'
    result = extract_translations(json_str)
    assert result == ["Xin chào", "Thế giới"]


def test_extract_translations_nested_format():
    """Test extraction from nested JSON with translations key."""
    json_str = '{"result": {"translations": ["Xin chào", "Thế giới"]}}'
    result = extract_translations(json_str)
    assert result == ["Xin chào", "Thế giới"]


def test_extract_translations_invalid_format():
    """Test that invalid JSON format raises ValueError."""
    with pytest.raises(ValueError):
        extract_translations('{"invalid": "format"}')


def test_extract_translations_fixes_control_chars():
    """Test that control characters are properly escaped."""
    # This simulates a response with unescaped control characters
    json_str = '{"translations": ["Hello\\nWorld", "Test\\tTab"]}'
    result = extract_translations(json_str)
    # Should handle the escaped characters properly
    assert len(result) == 2
