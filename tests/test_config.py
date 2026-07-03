"""Tests for configuration system."""

import os
import tempfile
from pathlib import Path

import pytest

from trans_epub.config import EngineConfig, GlobalConfig, get_api_key, load_config


def test_load_default_config():
    """Test loading config with default values."""
    config = load_config(None)  # Should load defaults

    assert config.engine in ["auto", "azure", "alibaba", "gemini", "deepseek"]
    assert config.threads == 4
    assert config.creativity is None


def test_load_config_from_env_vars():
    """Test that environment variables override config."""
    original_engine = os.environ.get("TRANS_EPUB_ENGINE")
    original_threads = os.environ.get("TRANS_EPUB_THREADS")

    try:
        os.environ["TRANS_EPUB_ENGINE"] = "alibaba"
        os.environ["TRANS_EPUB_THREADS"] = "8"

        config = load_config(None)

        assert config.engine == "alibaba"
        assert config.threads == 8

    finally:
        if original_engine is not None:
            os.environ["TRANS_EPUB_ENGINE"] = original_engine
        elif "TRANS_EPUB_ENGINE" in os.environ:
            del os.environ["TRANS_EPUB_ENGINE"]

        if original_threads is not None:
            os.environ["TRANS_EPUB_THREADS"] = original_threads
        elif "TRANS_EPUB_THREADS" in os.environ:
            del os.environ["TRANS_EPUB_THREADS"]


def test_get_api_key_from_env():
    """Test that API keys can be retrieved from environment."""
    original_key = os.environ.get("DASHSCOPE_API_KEY")

    try:
        os.environ["DASHSCOPE_API_KEY"] = "test_key_value"
        assert get_api_key("alibaba") == "test_key_value"
    finally:
        if original_key is not None:
            os.environ["DASHSCOPE_API_KEY"] = original_key
        elif "DASHSCOPE_API_KEY" in os.environ:
            del os.environ["DASHSCOPE_API_KEY"]


def test_config_structures():
    """Test that config classes have expected attributes."""
    engine_cfg = EngineConfig()
    assert hasattr(engine_cfg, "api_key")
    assert hasattr(engine_cfg, "base_url")
    assert hasattr(engine_cfg, "model")
    assert hasattr(engine_cfg, "creativity")

    global_cfg = GlobalConfig()
    assert hasattr(global_cfg, "engine")
    assert hasattr(global_cfg, "threads")
    assert hasattr(global_cfg, "creativity")
    assert hasattr(global_cfg, "engines")


def test_create_sample_config_file():
    """Test that a sample config file can be loaded."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(
            "[defaults]\n"
            'engine = "azure"\n'
            "threads = 4\n"
            "creativity = 0.3\n"
            "\n"
            "[engines.alibaba]\n"
            'api_key = "test_key"\n'
        )
        f.flush()

        config = load_config(Path(f.name))
        assert config.engine == "azure"
        assert config.threads == 4
        assert config.creativity == 0.3

        os.unlink(f.name)
