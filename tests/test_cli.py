"""Tests for the CLI module."""

import pytest

from trans_epub.cli import __version__, main, resolve_engine


class TestVersion:
    def test_flag_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0

    def test_variable_is_set(self):
        assert __version__ is not None
        assert __version__ != "unknown"
        assert isinstance(__version__, str)


class TestMainErrors:
    def test_missing_input_exits_code_2(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_bad_engine(self):
        with pytest.raises(SystemExit) as exc:
            main(["--engine", "nope", "in.epub"])
        assert exc.value.code == 2


class TestResolveEngine:
    """resolve_engine auto-detection."""

    def test_returns_given_name_when_not_auto(self):
        assert resolve_engine("gemini") == "gemini"

    def test_auto_detects_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "k")
        assert resolve_engine("auto") == "azure"

    def test_auto_prefers_azure_over_gemini(self, monkeypatch):
        monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "k")
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        assert resolve_engine("auto") == "azure"

    def test_auto_raises_when_no_key(self, monkeypatch):
        for var in (
            "AZURE_TRANSLATOR_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "DASHSCOPE_API_KEY",
            "GOOGLE_TRANSLATE_API_KEY",
            "DEEPL_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(RuntimeError, match="No translation API key found"):
            resolve_engine("auto")
