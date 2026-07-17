"""Tests for translation engine registry and shared utilities."""

from unittest.mock import patch

import pytest

from trans_epub.engines.base import ENGINES
from trans_epub.engines.base import (
    EngineConfig,
    extract_translations,
    translate_texts,
)


class TestEnginesRegistered:
    def test_all_expected_engines_present(self):
        expected = {"azure", "alibaba", "gemini", "deepseek", "google", "deepl"}
        assert expected.issubset(ENGINES.keys())

    def test_each_config_has_required_fields(self):
        for name, config in ENGINES.items():
            assert isinstance(config.name, str)
            assert callable(config.translate)
            assert isinstance(config.char_limit, int)
            assert isinstance(config.elem_limit, int)
            assert isinstance(config.delay, (int, float))


class TestTranslateTexts:
    """translate_texts dispatcher passes creativity to LLM engines only."""

    def test_passes_creativity_to_llm_engine(self):
        seen = {}

        def fake(texts, **kwargs):
            seen.update(kwargs)
            return texts

        cfg = EngineConfig(
            name="gemini", translate=fake, char_limit=100, elem_limit=10, delay=0
        )
        with patch.dict(ENGINES, {"gemini": cfg}):
            translate_texts("gemini", ["hello"], creativity=0.5)

        assert seen.get("creativity") == 0.5

    def test_does_not_pass_creativity_to_http_engine(self):
        seen = {}

        def fake(texts, **kwargs):
            seen.update(kwargs)
            return texts

        cfg = EngineConfig(
            name="azure", translate=fake, char_limit=100, elem_limit=10, delay=0
        )
        with patch.dict(ENGINES, {"azure": cfg}):
            translate_texts("azure", ["hello"], creativity=0.5)

        assert "creativity" not in seen

    def test_raises_on_missing_engine(self):
        with pytest.raises(KeyError):
            translate_texts("nonexistent", ["hello"])


class TestExtractTranslations:
    def test_basic(self):
        assert extract_translations('{"translations": ["Xin chào", "Thế giới"]}') == [
            "Xin chào",
            "Thế giới",
        ]

    def test_with_markdown_fence(self):
        result = extract_translations('```json\n{"translations": ["Xin chào"]}\n```')
        assert result == ["Xin chào"]

    def test_list_format(self):
        assert extract_translations('["A", "B"]') == ["A", "B"]

    def test_nested_format(self):
        result = extract_translations('{"result": {"translations": ["A", "B"]}}')
        assert result == ["A", "B"]

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            extract_translations('{"invalid": "format"}')

    def test_repairs_control_chars(self):
        result = extract_translations(
            '{"translations": ["Hello\\nWorld", "Test\\tTab"]}'
        )
        assert len(result) == 2
