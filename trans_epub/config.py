"""Configuration management for trans-epub."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


@dataclass
class EngineConfig:
    """Configuration for a specific translation engine."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    creativity: Optional[float] = None
    char_limit: Optional[int] = None
    elem_limit: Optional[int] = None
    region: Optional[str] = None  # For Azure specifically


@dataclass
class BatchingConfig:
    """Configuration for text batching."""

    char_limit: int = 10000
    elem_limit: int = 25
    delay: float = 0.0


@dataclass
class CachingConfig:
    """Configuration for caching."""

    enabled: bool = True
    ttl_days: int = 30
    location: str = "./cache"


@dataclass
class UIConfig:
    """Configuration for user interface."""

    progress_refresh_rate: float = 0.1
    verbose: bool = False


@dataclass
class GlobalConfig:
    """Global configuration for trans-epub."""

    engine: str = "azure"
    threads: int = 4
    creativity: Optional[float] = None
    timeout: int = 300

    engines: Dict[str, EngineConfig] = field(default_factory=dict)
    batching: BatchingConfig = field(default_factory=BatchingConfig)
    caching: CachingConfig = field(default_factory=CachingConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def load_config(config_path: Optional[Path] = None) -> GlobalConfig:
    """Load configuration from TOML file, with environment variable overrides."""
    if config_path is None:
        # Look for config in common locations
        possible_paths = [
            Path("./.trans-epub/config.toml"),
            Path("~/.config/trans-epub/config.toml").expanduser(),
            Path("/etc/trans-epub/config.toml"),
        ]

        for path in possible_paths:
            if path.exists():
                config_path = path
                break

    config_data = {}
    if config_path and config_path.exists():
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)

    # Create config with defaults
    cfg = GlobalConfig()

    # Override with config file values
    defaults = config_data.get("defaults", {})
    cfg.engine = defaults.get("engine", cfg.engine)
    cfg.threads = defaults.get("threads", cfg.threads)
    cfg.creativity = defaults.get("creativity", cfg.creativity)
    cfg.timeout = defaults.get("timeout", cfg.timeout)

    # Engine configs
    engine_configs = config_data.get("engines", {})
    for engine_name in ["azure", "alibaba", "gemini", "deepseek"]:
        if engine_name in engine_configs:
            engine_data = engine_configs[engine_name]
            cfg.engines[engine_name] = EngineConfig(
                api_key=engine_data.get("api_key"),
                base_url=engine_data.get("base_url"),
                model=engine_data.get("model"),
                creativity=engine_data.get("creativity"),
                char_limit=engine_data.get("char_limit"),
                elem_limit=engine_data.get("elem_limit"),
                region=engine_data.get("region"),
            )

    # Batching config
    batching_data = config_data.get("batching", {})
    cfg.batching = BatchingConfig(
        char_limit=batching_data.get("char_limit", cfg.batching.char_limit),
        elem_limit=batching_data.get("elem_limit", cfg.batching.elem_limit),
        delay=batching_data.get("delay", cfg.batching.delay),
    )

    # Caching config
    caching_data = config_data.get("caching", {})
    cfg.caching = CachingConfig(
        enabled=caching_data.get("enabled", cfg.caching.enabled),
        ttl_days=caching_data.get("ttl_days", cfg.caching.ttl_days),
        location=caching_data.get("location", cfg.caching.location),
    )

    # UI config
    ui_data = config_data.get("ui", {})
    cfg.ui = UIConfig(
        progress_refresh_rate=ui_data.get(
            "progress_refresh_rate", cfg.ui.progress_refresh_rate
        ),
        verbose=ui_data.get("verbose", cfg.ui.verbose),
    )

    # Override with environment variables (highest priority)
    cfg.engine = os.getenv("TRANS_EPUB_ENGINE", cfg.engine)
    if "TRANS_EPUB_THREADS" in os.environ:
        cfg.threads = int(os.getenv("TRANS_EPUB_THREADS", str(cfg.threads)))
    if "TRANS_EPUB_CREATIVITY" in os.environ:
        cfg.creativity = float(os.getenv("TRANS_EPUB_CREATIVITY", str(cfg.creativity)))
    if "TRANS_EPUB_TIMEOUT" in os.environ:
        cfg.timeout = int(os.getenv("TRANS_EPUB_TIMEOUT", str(cfg.timeout)))

    return cfg


def get_api_key(engine: str) -> Optional[str]:
    """Get API key for engine, checking config and environment variables."""
    # Check environment variables first
    env_vars = {
        "azure": ["AZURE_TRANSLATOR_KEY", "TRANS_EPUB_AZURE_KEY"],
        "alibaba": ["DASHSCOPE_API_KEY", "TRANS_EPUB_ALIBABA_KEY"],
        "gemini": ["GEMINI_API_KEY", "TRANS_EPUB_GEMINI_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY", "TRANS_EPUB_DEEPSEEK_KEY"],
    }

    for env_var in env_vars.get(engine, []):
        key = os.getenv(env_var)
        if key:
            return key

    # Fall back to config file
    config = load_config()
    engine_cfg = config.engines.get(engine)
    if engine_cfg:
        return engine_cfg.api_key

    return None
