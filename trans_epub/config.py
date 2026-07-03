"""Configuration system for trans-epub.

Supports loading from:
  - ./.trans-epub/config.toml  (project-local)
  - ~/.config/trans-epub/config.toml  (user-global)
  - An explicit path passed to load_config()
  - TRANS_EPUB_* environment variables (override file config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EngineConfig:
    """Per-engine overrides (API key, base URL, model, creativity)."""

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    creativity: float | None = None


@dataclass
class GlobalConfig:
    """Top-level configuration object."""

    engine: str = "auto"
    threads: int = 4
    creativity: float | None = None
    engines: dict[str, EngineConfig] = field(default_factory=dict)


# ── Default search paths ──────────────────────────────────────────────────────

_DEFAULT_PATHS: list[Path] = [
    Path(".trans-epub") / "config.toml",
    Path.home() / ".config" / "trans-epub" / "config.toml",
]

# Map engine name → env-var name for API keys
_ENGINE_KEY_ENV: dict[str, str] = {
    "azure": "AZURE_TRANSLATOR_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "alibaba": "DASHSCOPE_API_KEY",
    "google": "GOOGLE_TRANSLATE_API_KEY",
    "deepl": "DEEPL_API_KEY",
}


# ── Public API ────────────────────────────────────────────────────────────────


def load_config(path: Path | None = None) -> GlobalConfig:
    """Load configuration from *path*, the default search paths, or env vars.

    Priority (highest → lowest):
      1. TRANS_EPUB_* environment variables
      2. Explicit *path* argument
      3. First found file in _DEFAULT_PATHS
      4. Built-in defaults
    """
    cfg = GlobalConfig()

    # Try to load from file
    config_file: Path | None = path
    if config_file is None:
        for candidate in _DEFAULT_PATHS:
            if candidate.exists():
                config_file = candidate
                break

    if config_file is not None and config_file.exists():
        _apply_toml(cfg, config_file)

    # Environment variable overrides
    if env_engine := os.environ.get("TRANS_EPUB_ENGINE"):
        cfg.engine = env_engine
    if env_threads := os.environ.get("TRANS_EPUB_THREADS"):
        try:
            cfg.threads = int(env_threads)
        except ValueError:
            pass
    if env_creativity := os.environ.get("TRANS_EPUB_CREATIVITY"):
        try:
            cfg.creativity = float(env_creativity)
        except ValueError:
            pass

    return cfg


def get_api_key(engine: str) -> str | None:
    """Return the API key for *engine* from environment variables."""
    env_var = _ENGINE_KEY_ENV.get(engine)
    if env_var:
        return os.environ.get(env_var)
    return None


# ── TOML loading (stdlib tomllib, Python 3.11+) ───────────────────────────────


def _apply_toml(cfg: GlobalConfig, path: Path) -> None:
    """Parse *path* as TOML and apply values to *cfg* in-place."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return  # TOML not available; silently skip

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    defaults = data.get("defaults", {})
    if "engine" in defaults:
        cfg.engine = str(defaults["engine"])
    if "threads" in defaults:
        cfg.threads = int(defaults["threads"])
    if "creativity" in defaults:
        cfg.creativity = float(defaults["creativity"])

    # [engines.<name>] sections
    for eng_name, eng_data in data.get("engines", {}).items():
        ec = EngineConfig()
        if "api_key" in eng_data:
            ec.api_key = str(eng_data["api_key"])
        if "base_url" in eng_data:
            ec.base_url = str(eng_data["base_url"])
        if "model" in eng_data:
            ec.model = str(eng_data["model"])
        if "creativity" in eng_data:
            ec.creativity = float(eng_data["creativity"])
        cfg.engines[eng_name] = ec
