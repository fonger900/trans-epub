"""Tests for configuration system."""

import os
import tempfile
from pathlib import Path

from trans_epub.config import EngineConfig, GlobalConfig, get_api_key, load_config


class TestLoadConfig:
    def test_default_values(self):
        config = load_config(None)
        assert config.engine == "auto"
        assert config.threads == 4
        assert config.creativity is None

    def test_env_var_overrides(self, monkeypatch):
        monkeypatch.setenv("TRANS_EPUB_ENGINE", "alibaba")
        monkeypatch.setenv("TRANS_EPUB_THREADS", "8")
        monkeypatch.setenv("TRANS_EPUB_CREATIVITY", "0.7")
        config = load_config(None)
        assert config.engine == "alibaba"
        assert config.threads == 8
        assert config.creativity == 0.7

    def test_toml_file_loading(self):
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

    def test_env_overrides_toml(self, monkeypatch):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[defaults]\nengine = "azure"\nthreads = 4\n')
            f.flush()
            monkeypatch.setenv("TRANS_EPUB_ENGINE", "gemini")
            config = load_config(Path(f.name))
            assert config.engine == "gemini"  # env wins
            assert config.threads == 4  # from file
            os.unlink(f.name)


class TestGetApiKey:
    def test_returns_env_var(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test_key_value")
        assert get_api_key("alibaba") == "test_key_value"

    def test_returns_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        assert get_api_key("alibaba") is None

    def test_returns_none_for_unknown_engine(self):
        assert get_api_key("nonexistent") is None

    def test_maps_correct_env_var(self, monkeypatch):
        pairs = [
            ("azure", "AZURE_TRANSLATOR_KEY"),
            ("gemini", "GEMINI_API_KEY"),
            ("deepseek", "DEEPSEEK_API_KEY"),
            ("alibaba", "DASHSCOPE_API_KEY"),
            ("google", "GOOGLE_TRANSLATE_API_KEY"),
            ("deepl", "DEEPL_API_KEY"),
        ]
        for engine, env_var in pairs:
            monkeypatch.setenv(env_var, f"val_{engine}")
            assert get_api_key(engine) == f"val_{engine}"


class TestConfigStructures:
    def test_engine_config_attributes(self):
        cfg = EngineConfig()
        assert hasattr(cfg, "api_key")
        assert hasattr(cfg, "base_url")
        assert hasattr(cfg, "model")
        assert hasattr(cfg, "creativity")

    def test_global_config_attributes(self):
        cfg = GlobalConfig()
        assert hasattr(cfg, "engine")
        assert hasattr(cfg, "threads")
        assert hasattr(cfg, "creativity")
        assert hasattr(cfg, "engines")
        assert isinstance(cfg.engines, dict)
