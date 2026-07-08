"""Configuration system for trans-epub.

Unified config + glossary loading with shared TOML helpers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ── Search paths ──────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(".trans-epub")
_USER_CONFIG_DIR = Path.home() / ".config" / "trans-epub"


def _find_file(filename: str) -> Path | None:
    """Find file in project-local then user-global config dirs."""
    for base in [_CONFIG_DIR, _USER_CONFIG_DIR]:
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


# ── TOML loading ──────────────────────────────────────────────────────────────


def _load_toml(path: Path) -> dict:
    """Load TOML file, return empty dict on failure."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Main config ───────────────────────────────────────────────────────────────


@dataclass
class GlobalConfig:
    """Top-level configuration."""

    engine: str = "auto"
    threads: int = 4
    creativity: float | None = None


def load_config(path: Path | None = None) -> GlobalConfig:
    """Load config from file + env vars.

    Priority: env vars > explicit path > auto-detect > defaults
    """
    cfg = GlobalConfig()

    # File config
    config_file = path or _find_file("config.toml")
    if config_file:
        data = _load_toml(config_file)
        defaults = data.get("defaults", {})
        if "engine" in defaults:
            cfg.engine = str(defaults["engine"])
        if "threads" in defaults:
            cfg.threads = int(defaults["threads"])
        if "creativity" in defaults:
            cfg.creativity = float(defaults["creativity"])

    # Env overrides
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


# ── Glossary ──────────────────────────────────────────────────────────────────


@dataclass
class CharacterEntry:
    """Pronoun mapping for a character."""

    self_ref: str | None = None  # xưng (self-reference)
    address: str | None = None  # hô (how others address them)
    narrator: str | None = None  # narrator reference
    note: str | None = None  # context (age, role, relationship)

    def is_empty(self) -> bool:
        return not any([self.self_ref, self.address, self.narrator, self.note])


@dataclass
class Glossary:
    """Translation glossary with character pronouns and term mappings."""

    characters: dict[str, CharacterEntry] = field(default_factory=dict)
    terms: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.characters and not self.terms


def load_glossary(path: Path | None = None) -> Glossary | None:
    """Load glossary from path or auto-detect.

    Returns None if not found or empty.
    """
    glossary_file = path or _find_file("glossary.toml")
    if not glossary_file:
        return None

    data = _load_toml(glossary_file)
    if not data:
        return None

    characters: dict[str, CharacterEntry] = {}
    for name, entry in data.get("characters", {}).items():
        if isinstance(entry, str):
            # Simple form: John = "anh"
            characters[name] = CharacterEntry(address=entry)
        elif isinstance(entry, dict):
            char = CharacterEntry(
                self_ref=entry.get("self"),
                address=entry.get("form"),
                narrator=entry.get("narrator"),
                note=entry.get("note"),
            )
            if not char.is_empty():
                characters[name] = char

    terms: dict[str, str] = data.get("terms", {})

    glossary = Glossary(characters=characters, terms=terms)
    return None if glossary.is_empty() else glossary


def build_glossary_prompt(glossary: Glossary) -> str:
    """Build prompt section from glossary for LLM injection."""
    if glossary.is_empty():
        return ""

    parts = ["\nGlossary (follow strictly for consistency):"]

    if glossary.characters:
        parts.append("Characters (pronouns):")
        for name, entry in glossary.characters.items():
            details = []
            if entry.self_ref:
                details.append(f'self="{entry.self_ref}"')
            if entry.address:
                details.append(f'address="{entry.address}"')
            if entry.narrator:
                details.append(f'narrator="{entry.narrator}"')
            detail_str = ", ".join(details)
            if entry.note:
                detail_str += f" — {entry.note}"
            parts.append(f"• {name}: {detail_str}")

    if glossary.terms:
        parts.append("Terms:")
        for eng, vi in glossary.terms.items():
            parts.append(f'• "{eng}" → "{vi}"')

    return "\n".join(parts) + "\n"
