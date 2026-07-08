# Tests for configuration system.

import os
import tempfile
from pathlib import Path

from trans_epub.config import GlobalConfig, load_config


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
            f.write('[defaults]\nengine = "azure"\nthreads = 4\ncreativity = 0.3\n\n')
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


class TestConfigStructures:
    def test_global_config_attributes(self):
        cfg = GlobalConfig()
        assert hasattr(cfg, "engine")
        assert hasattr(cfg, "threads")
        assert hasattr(cfg, "creativity")
